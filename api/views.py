from rest_framework import viewsets, views, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta

import secrets
import hashlib
from django.db import connection
from django.http import JsonResponse
from django.conf import settings
from .models import Product, Order, Contact, UserProfile, Cart, CartItem, Delivery, OTPToken
from .serializers import (ProductSerializer, OrderSerializer, ContactSerializer,
                          UserSerializer, CartSerializer, CartItemSerializer, DeliverySerializer)
from .emails import (
    dispatch_otp_email_async,
    dispatch_order_confirmation_email_async,
    dispatch_order_status_email_async,
    dispatch_contact_notification_async,
)

def custom_500_handler(request, *args, **kwargs):
    response = JsonResponse({'error': 'Internal Server Error'}, status=500)
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = '*'
    response['Access-Control-Allow-Methods'] = '*'
    return response

def custom_exception_handler(exc, context):
    from rest_framework.views import exception_handler
    response = exception_handler(exc, context)
    if response is None:
        import traceback
        traceback.print_exc()
        res = Response({'error': f'Server Error: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        res['Access-Control-Allow-Origin'] = '*'
        return res
    return response

from django.contrib.sessions.models import Session

def flush_user_sessions(user):
    """Terminates all active Django session records for the specified user."""
    try:
        user_id_str = str(user.id)
        for session in Session.objects.all():
            try:
                data = session.get_decoded()
                if str(data.get('_auth_user_id')) == user_id_str:
                    session.delete()
            except Exception:
                pass
    except Exception as e:
        print(f"[SESSION FLUSH NOTICE] {e}")

from .permissions import (IsAdminUserOnly, IsAdminOrReadOnly, 
                          IsAdminOrContactSubmit, IsAdminOrOrderPlacement)

def issue_fresh_token(user):
    """
    Enforces logout from all other devices on new login and generates a brand new 
    token with a full 24-hour lifespan starting from right now.
    """
    Token.objects.filter(user=user).delete()
    return Token.objects.create(user=user)

def hash_otp(otp_code):
    return hashlib.sha256(f"{settings.SECRET_KEY}:{otp_code}".encode()).hexdigest()



# --- HEALTH CHECK (Keep-Alive & Fast Wakeup) ---
class HealthCheckView(views.APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        db_ok = True
        try:
            connection.ensure_connection()
        except Exception:
            db_ok = False
        response = Response({
            'status': 'ok' if db_ok else 'degraded',
            'database': 'connected' if db_ok else 'unavailable',
            'email_configured': bool(
                getattr(settings, 'RESEND_API_KEY', '').strip()
                or getattr(settings, 'EMAIL_HOST_USER', '').strip()
            ),
        })
        response['Cache-Control'] = 'no-store'
        return response


# --- PRODUCTS & CONTACTS ---
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = Product.objects.all().order_by('-created_at')
        include_inactive = self.request.query_params.get('include_inactive') == '1'
        is_admin = self.request.user and self.request.user.is_authenticated and (
            self.request.user.is_staff or self.request.user.is_superuser
        )
        if self.action == 'list' and not (include_inactive and is_admin):
            qs = qs.filter(isActive=True)
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        is_admin = request.user and request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser
        )
        if not is_admin:
            response['Cache-Control'] = 'public, max-age=60, stale-while-revalidate=300'
        return response


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all().order_by('-created_at')
    serializer_class = ContactSerializer
    permission_classes = [IsAdminOrContactSubmit]

    def perform_create(self, serializer):
        contact = serializer.save()
        dispatch_contact_notification_async(contact)

    @action(detail=True, methods=['patch'])
    def read(self, request, pk=None):
        contact = self.get_object()
        contact.is_read = True
        contact.save()
        return Response({'status': 'Contact marked as read'})

# --- ORDERS & DELIVERIES ---
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [IsAdminOrOrderPlacement]

    def perform_create(self, serializer):
        order = serializer.save()
        dispatch_order_confirmation_email_async(order)

    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required to view your orders.'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Return orders linked directly or by user email
        orders = Order.objects.filter(
            Q(user=request.user) | (Q(customer_email__iexact=request.user.email) if request.user.email else Q())
        ).order_by('-created_at')
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch', 'post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        is_admin = request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)
        is_owner = request.user.is_authenticated and (
            order.user_id == request.user.id
            or (order.customer_email and request.user.email and order.customer_email.lower() == request.user.email.lower())
        )
        if not (is_admin or is_owner):
            return Response({'error': 'You do not have permission to cancel this order.'}, status=status.HTTP_403_FORBIDDEN)

        current_status = (order.status or '').lower()
        if current_status in ['delivered', 'cancelled'] and not is_admin:
            return Response(
                {'error': f'Order cannot be cancelled as it is already marked as {order.status}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = 'cancelled'
        order.save()

        if hasattr(order, 'delivery'):
            order.delivery.status = 'cancelled'
            order.delivery.save()

        dispatch_order_status_email_async(order, 'cancelled')

        return Response({
            'status': 'cancelled',
            'message': 'Order successfully cancelled.',
            'order': self.get_serializer(order).data
        })

    @action(detail=True, methods=['post'])
    def reorder(self, request, pk=None):
        """Copy all matching products from a past order back into the authenticated user's cart."""
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        order = self.get_object()
        cart, _ = Cart.objects.get_or_create(user=request.user)
        added_count = 0
        for item in order.items.all():
            product = None
            if item.product_id:
                product = Product.objects.filter(id=item.product_id, isActive=True).first()
            if not product and item.product_name:
                product = Product.objects.filter(name__iexact=item.product_name, isActive=True).first()
            if product:
                cart_item, created = CartItem.objects.get_or_create(
                    cart=cart,
                    product=product,
                    selected_size=item.selected_size or '',
                    selected_color=item.selected_color or '',
                    defaults={'quantity': max(1, int(item.quantity or 1))}
                )
                if not created:
                    cart_item.quantity += max(1, int(item.quantity or 1))
                    cart_item.save()
                added_count += 1

        return Response({
            'status': 'ok',
            'added_count': added_count,
            'cart': CartSerializer(cart).data,
        })

    @action(detail=True, methods=['get'])
    def track(self, request, pk=None):
        order = self.get_object()
        delivery = getattr(order, 'delivery', None)
        curr_status = (order.status or 'pending').lower()

        # Build chronological tracker matching Amazon / Flipkart e-commerce convention
        created = order.created_at
        timeline = [
            {
                'key': 'placed',
                'title': 'Order Confirmed',
                'description': 'Your order has been placed and received by store.',
                'timestamp': created,
                'completed': True,
                'current': curr_status == 'pending'
            },
            {
                'key': 'processing',
                'title': 'Packed & Processed',
                'description': 'Seller is preparing your package for courier pickup.',
                'timestamp': (created + timedelta(hours=6)) if curr_status in ['processing', 'shipped', 'delivered'] else None,
                'completed': curr_status in ['processing', 'shipped', 'delivered'],
                'current': curr_status == 'processing'
            },
            {
                'key': 'shipped',
                'title': 'Shipped / In Transit',
                'description': f"Dispatched with {delivery.carrier if delivery and delivery.carrier else 'Express Courier'}. Tracking ID: {delivery.tracking_number if delivery else 'Pending'}",
                'timestamp': (created + timedelta(days=1)) if curr_status in ['shipped', 'delivered'] else None,
                'completed': curr_status in ['shipped', 'delivered'],
                'current': curr_status == 'shipped'
            },
            {
                'key': 'delivered',
                'title': 'Delivered',
                'description': 'Package delivered safely to destination address.',
                'timestamp': (delivery.estimated_delivery if delivery and delivery.estimated_delivery else created + timedelta(days=4)) if curr_status == 'delivered' else None,
                'completed': curr_status == 'delivered',
                'current': curr_status == 'delivered'
            }
        ]

        if curr_status == 'cancelled':
            timeline.append({
                'key': 'cancelled',
                'title': 'Order Cancelled',
                'description': 'This order was cancelled.',
                'timestamp': order.created_at,
                'completed': True,
                'current': True
            })

        return Response({
            'order_id': order.id,
            'status': order.status,
            'timeline': timeline,
            'delivery': DeliverySerializer(delivery).data if delivery else None
        })

    @action(detail=True, methods=['patch'])
    def status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        if new_status:
            order.status = new_status
            order.save()
            # Also update delivery if it exists
            if hasattr(order, 'delivery'):
                order.delivery.status = new_status
                order.delivery.save()
            dispatch_order_status_email_async(order, new_status)
            return Response({'status': 'Order status updated', 'order': self.get_serializer(order).data})
        return Response({'error': 'Status not provided'}, status=400)

class DeliveryViewSet(viewsets.ModelViewSet):
    queryset = Delivery.objects.all().order_by('-updated_at')
    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    @action(detail=True, methods=['patch'])
    def status(self, request, pk=None):
        delivery = self.get_object()
        new_status = request.data.get('status')
        if new_status:
            delivery.status = new_status
            delivery.save()
            delivery.order.status = new_status
            delivery.order.save()
            dispatch_order_status_email_async(delivery.order, new_status)
            return Response({'status': 'Delivery status updated'})
        return Response({'error': 'Status not provided'}, status=400)

# --- CART ---
class CartViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_cart(self, user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    def list(self, request):
        cart = self.get_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add(self, request):
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))
        selected_size = request.data.get('selected_size', '') or ''
        selected_color = request.data.get('selected_color', '') or ''
        
        try:
            product = Product.objects.get(id=product_id)
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart, 
                product=product,
                selected_size=selected_size,
                selected_color=selected_color,
                defaults={'quantity': quantity}
            )
            if not created:
                cart_item.quantity += quantity
                cart_item.save()
            return Response({'status': 'Product added to cart'})
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        cart = self.get_cart(request.user)
        cart.items.all().delete()
        return Response({'status': 'Cart cleared'})

    # For individual cart items (PUT/DELETE)
    def _find_cart_item(self, request, pk):
        qs = CartItem.objects.filter(cart__user=request.user).filter(Q(id=pk) | Q(product__id=pk))
        selected_size = request.data.get('selected_size') if hasattr(request, 'data') else None
        selected_color = request.data.get('selected_color') if hasattr(request, 'data') else None
        if selected_size is None:
            selected_size = request.query_params.get('selected_size')
        if selected_color is None:
            selected_color = request.query_params.get('selected_color')
        if selected_size is not None or selected_color is not None:
            exact = qs.filter(
                selected_size=selected_size or '',
                selected_color=selected_color or '',
            ).first()
            if exact:
                return exact
        return qs.first()

    def update_item(self, request, pk=None):
        try:
            item = self._find_cart_item(request, pk)
            if not item:
                return Response({'error': 'Item not in cart'}, status=404)
            item.quantity = max(1, int(request.data.get('quantity', 1)))
            item.save()
            return Response({'status': 'Quantity updated'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    def destroy_item(self, request, pk=None):
        try:
            item = self._find_cart_item(request, pk)
            if not item:
                return Response({'error': 'Item not in cart'}, status=404)
            item.delete()
            return Response({'status': 'Item removed'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

# --- AUTH & USER PROFILE ---
class AuthView(views.APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, action=None):
        try:
            if action == 'send-otp':
                email = (request.data.get('email') or '').strip().lower()
                if not email:
                    return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

                now = timezone.now()
                # Rate limiting / Cooldown check (30 seconds)
                try:
                    recent_otp = OTPToken.objects.filter(email=email, created_at__gte=now - timedelta(seconds=30)).first()
                    if recent_otp:
                        return Response({'error': 'Please wait 30 seconds before requesting another OTP.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
                except Exception as db_err:
                    print(f"[OTP DB ERROR] {db_err}")

                # Generate cryptographically secure 6-digit OTP
                otp_code = ''.join([secrets.choice('0123456789') for _ in range(6)])
                otp_hash_val = hash_otp(otp_code)
                expires_at = now + timedelta(minutes=5)

                # Save OTP Token in DB
                try:
                    OTPToken.objects.create(
                        email=email,
                        otp_hash=otp_hash_val,
                        expires_at=expires_at
                    )
                except Exception as create_err:
                    print(f"[OTP TOKEN CREATE ERROR] {create_err}")

                # Send OTP Email asynchronously in background daemon thread (instant HTTP response)
                dispatch_otp_email_async(email, otp_code)

                resp_data = {
                    'message': f'OTP code sent to {email}. Please check your inbox.',
                    'email': email,
                    'expires_in': 300
                }
                if settings.DEBUG:
                    resp_data['debug_otp'] = otp_code

                return Response(resp_data, status=status.HTTP_200_OK)


            elif action == 'verify-otp':
                email = (request.data.get('email') or '').strip().lower()
                otp_code = (request.data.get('otp') or '').strip()

                if not email or not otp_code:
                    return Response({'error': 'Email and OTP code are required'}, status=status.HTTP_400_BAD_REQUEST)

                now = timezone.now()
                otp_token = OTPToken.objects.filter(email=email, is_used=False).order_by('-created_at').first()

                if not otp_token:
                    return Response({'error': 'No OTP request found for this email. Please request a new code.'}, status=status.HTTP_400_BAD_REQUEST)

                if otp_token.expires_at < now:
                    otp_token.is_used = True
                    otp_token.save()
                    return Response({'error': 'OTP code has expired. Please request a new code.'}, status=status.HTTP_400_BAD_REQUEST)

                if otp_token.attempts >= 5:
                    otp_token.is_used = True
                    otp_token.save()
                    return Response({'error': 'Too many failed attempts. Please request a new OTP code.'}, status=status.HTTP_400_BAD_REQUEST)

                # Verify OTP hash
                if hash_otp(otp_code) != otp_token.otp_hash:
                    otp_token.attempts += 1
                    otp_token.save()
                    remaining_attempts = 5 - otp_token.attempts
                    return Response({'error': f'Invalid OTP code. {remaining_attempts} attempt(s) remaining.'}, status=status.HTTP_400_BAD_REQUEST)

                # Valid OTP!
                otp_token.is_used = True
                otp_token.save()

                # Find or Create User
                user = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).first()
                if not user:
                    # Auto register user with email as username
                    user = User.objects.create_user(username=email, email=email)
                    UserProfile.objects.create(user=user)
                elif not hasattr(user, 'profile'):
                    UserProfile.objects.create(user=user)

                token = issue_fresh_token(user)
                return Response({
                    'token': token.key,
                    'user': UserSerializer(user).data,
                    'message': 'Logged in successfully via OTP!'
                }, status=status.HTTP_200_OK)

            elif action == 'login':
                username = request.data.get('username') or request.data.get('email')
                password = request.data.get('password')
                user = authenticate(username=username, password=password)
                if user:
                    token = issue_fresh_token(user)
                    return Response({'token': token.key, 'user': UserSerializer(user).data})
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
                
            elif action == 'register':
                username = request.data.get('username') or request.data.get('email')
                email = request.data.get('email')
                password = request.data.get('password')
                if User.objects.filter(username=username).exists():
                    return Response({'error': 'Username/Email already exists'}, status=400)
                
                user = User.objects.create_user(username=username, email=email, password=password)
                UserProfile.objects.create(user=user)
                token = issue_fresh_token(user)
                return Response({'token': token.key, 'user': UserSerializer(user).data})

            elif action == 'logout':
                if request.user.is_authenticated:
                    Token.objects.filter(user=request.user).delete()
                    flush_user_sessions(request.user)
                else:
                    auth_header = request.headers.get('Authorization', '')
                    if auth_header.startswith('Token '):
                        token_key = auth_header.split(' ')[1]
                        Token.objects.filter(key=token_key).delete()
                return Response({'status': 'Logged out successfully'})

            elif action in ['logout-all', 'logout_all']:
                target_user = None
                if request.user.is_authenticated:
                    target_user = request.user
                else:
                    auth_header = request.headers.get('Authorization', '')
                    if auth_header.startswith('Token '):
                        token_key = auth_header.split(' ')[1]
                        token_obj = Token.objects.filter(key=token_key).select_related('user').first()
                        if token_obj:
                            target_user = token_obj.user
                if target_user:
                    Token.objects.filter(user=target_user).delete()
                    flush_user_sessions(target_user)
                    return Response({'status': 'Successfully logged out from all devices and sessions.'})
                return Response({'status': 'Logged out successfully'})
        except Exception as general_err:
            import traceback
            traceback.print_exc()
            return Response({'error': f'Internal Server Error: {str(general_err)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class UserProfileView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        user = request.user
        if 'name' in request.data:
            user.first_name = request.data.get('name')
        elif 'first_name' in request.data:
            user.first_name = request.data.get('first_name')
        if 'last_name' in request.data:
            user.last_name = request.data.get('last_name')
        user.save()
        
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if 'phone' in request.data:
            profile.phone = request.data.get('phone')
        if 'address' in request.data:
            profile.address = request.data.get('address')
        if 'saved_addresses' in request.data:
            addrs = request.data.get('saved_addresses')
            if isinstance(addrs, list):
                profile.saved_addresses = addrs
        if 'age' in request.data:
            try:
                profile.age = int(request.data.get('age')) if request.data.get('age') else None
            except (ValueError, TypeError):
                profile.age = None
        if 'gender' in request.data:
            profile.gender = request.data.get('gender')
        profile.save()
        
        return Response(UserSerializer(user).data)

# --- ADMIN AUTH ---
class AdminLoginView(views.APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        username_or_email = (
            request.data.get('username') or 
            request.data.get('email') or 
            request.data.get('user') or 
            ''
        ).strip()
        password = (request.data.get('password') or '').strip()

        if not username_or_email or not password:
            return Response({'error': 'Username/Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Lookup user by username or email
        user_obj = User.objects.filter(
            Q(username__iexact=username_or_email) | Q(email__iexact=username_or_email)
        ).first()

        user = None
        if user_obj and user_obj.check_password(password):
            user = user_obj
        else:
            user = authenticate(username=username_or_email, password=password)

        if not user:
            return Response({'error': 'Invalid username/email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({'error': 'This account has been deactivated.'}, status=status.HTTP_403_FORBIDDEN)

        # STRICT PRIVILEGE CHECK: Under NO circumstances promote non-staff or allow customer accounts
        if not (user.is_staff or user.is_superuser):
            return Response({
                'error': 'Access denied. Administrator privileges are required to access this portal.'
            }, status=status.HTTP_403_FORBIDDEN)

        token = issue_fresh_token(user)
        return Response({
            'token': token.key,
            'user': {
                'username': user.username,
                'email': user.email,
                'role': 'superadmin' if user.is_superuser else 'admin',
                'loginTime': timezone.now().isoformat(),
            }
        })


class AdminLogoutView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        Token.objects.filter(user=user).delete()
        flush_user_sessions(user)
        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class AdminLogoutAllView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        # Revoke all tokens across all devices
        Token.objects.filter(user=user).delete()
        # Invalidate all server sessions
        flush_user_sessions(user)
        return Response({'message': 'Successfully logged out from all devices.'}, status=status.HTTP_200_OK)


# --- CHANGE PASSWORD ---
class ChangePasswordView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password', '').strip()
        new_password = request.data.get('new_password', '').strip()
        confirm_password = request.data.get('confirm_password', '').strip()

        if not current_password or not new_password or not confirm_password:
            return Response({'error': 'All fields are required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        if not user.check_password(current_password):
            return Response({'error': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({'error': 'New password and confirm password do not match.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({'error': 'New password must be at least 8 characters long.'}, status=status.HTTP_400_BAD_REQUEST)

        # Enforce Django password validators
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        # Set new password
        user.set_password(new_password)
        user.save()

        # LOGOUT EVERYWHERE:
        # Invalidate existing token(s) and sessions across all devices
        flush_user_sessions(user)

        # Generate a fresh token for the current active session (24h lifespan)
        new_token = issue_fresh_token(user)

        return Response({
            'message': 'Password updated successfully! All other sessions and devices have been logged out.',
            'token': new_token.key
        }, status=status.HTTP_200_OK)

# --- ANALYTICS ---
class AnalyticsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        total_orders = Order.objects.count()
        total_revenue = Order.objects.aggregate(Sum('total'))['total__sum'] or 0
        total_products = Product.objects.count()
        recent_orders = OrderSerializer(Order.objects.order_by('-created_at')[:5], many=True).data
        return Response({
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'total_products': total_products,
            'recent_orders': recent_orders
        })

