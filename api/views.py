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
from django.core.mail import send_mail
from django.http import JsonResponse
from django.conf import settings
from .models import Product, Order, Contact, UserProfile, Cart, CartItem, Delivery, OTPToken
from .serializers import (ProductSerializer, OrderSerializer, ContactSerializer,
                          UserSerializer, CartSerializer, CartItemSerializer, DeliverySerializer)

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

def hash_otp(otp_code):
    return hashlib.sha256(f"{settings.SECRET_KEY}:{otp_code}".encode()).hexdigest()



# --- PRODUCTS & CONTACTS ---
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all().order_by('-created_at')
    serializer_class = ContactSerializer

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
            return Response({'status': 'Order status updated'})
        return Response({'error': 'Status not provided'}, status=400)

class DeliveryViewSet(viewsets.ModelViewSet):
    queryset = Delivery.objects.all().order_by('-updated_at')
    serializer_class = DeliverySerializer

    @action(detail=True, methods=['patch'])
    def status(self, request, pk=None):
        delivery = self.get_object()
        new_status = request.data.get('status')
        if new_status:
            delivery.status = new_status
            delivery.save()
            delivery.order.status = new_status
            delivery.order.save()
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
        
        try:
            product = Product.objects.get(id=product_id)
            cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
            if not created:
                cart_item.quantity += quantity
            else:
                cart_item.quantity = quantity
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
    def update_item(self, request, pk=None):
        try:
            item = CartItem.objects.get(product__id=pk, cart__user=request.user)
            item.quantity = int(request.data.get('quantity', 1))
            item.save()
            return Response({'status': 'Quantity updated'})
        except CartItem.DoesNotExist:
            return Response({'error': 'Item not in cart'}, status=404)

    def destroy_item(self, request, pk=None):
        try:
            item = CartItem.objects.get(product__id=pk, cart__user=request.user)
            item.delete()
            return Response({'status': 'Item removed'})
        except CartItem.DoesNotExist:
            return Response({'error': 'Item not in cart'}, status=404)

def generate_otp_html_email(otp_code):
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Verification Code</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 30px 15px; color: #1e293b;">
    <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01); border: 1px solid #e2e8f0;">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); padding: 36px 24px; text-align: center; color: #ffffff;">
            <div style="font-size: 28px; font-weight: 900; letter-spacing: -0.5px; margin-bottom: 4px;">Eacyclic</div>
            <div style="font-size: 13px; font-weight: 500; color: rgba(255, 255, 255, 0.9); text-transform: uppercase; letter-spacing: 1px;">Secure Sign In</div>
        </div>
        
        <!-- Content -->
        <div style="padding: 36px 32px; text-align: center;">
            <div style="font-size: 20px; font-weight: 800; color: #0f172a; margin-bottom: 8px;">Your Authentication Code</div>
            <div style="font-size: 14px; color: #64748b; line-height: 1.6; margin-bottom: 28px;">
                Use the verification code below to log in to your Eacyclic account.
            </div>
            
            <!-- OTP Badge -->
            <div style="background: #fff7ed; border: 1.5px solid #ffedd5; border-radius: 16px; padding: 8px 12px; margin: 0 auto 28px auto; text-align: center;">
                <div style="font-size: 24px; font-weight: 900; letter-spacing: 12px; color: #000000; font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, monospace; margin-left: 12px;">{otp_code}</div>
                <div style="display: inline-block; background-color: #ffedd5; color: #c2410c; font-size: 12px; font-weight: 700; padding: 4px 12px; border-radius: 20px; margin-top: 14px;">Valid for 5 minutes</div>
            </div>

            <!-- Security Alert -->
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 12px; text-align: left; font-size: 13px; color: #475569; line-height: 1.5;">
                <strong style="color: #0f172a;">Security Notice:</strong> If you did not request this code, please ignore this email. Do not share this code with anyone.
            </div>
        </div>
        
        <!-- Footer -->
        <div style="background-color: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #f1f5f9;">
            &copy; {timezone.now().year} Eacyclic. All rights reserved.
        </div>
    </div>
</body>
</html>"""

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
                # Rate limiting / Cooldown check (60 seconds)
                try:
                    recent_otp = OTPToken.objects.filter(email=email, created_at__gte=now - timedelta(seconds=60)).first()
                    if recent_otp:
                        return Response({'error': 'Please wait 60 seconds before requesting another OTP.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
                except Exception as db_err:
                    print(f"[OTP DB ERROR] {db_err}")

                # Generate cryptographically secure 6-digit OTP
                otp_code = ''.join([secrets.choice('0123456789') for _ in range(6)])
                otp_hash_val = hash_otp(otp_code)
                expires_at = now + timedelta(minutes=5)

                # Save OTP Token
                try:
                    OTPToken.objects.create(
                        email=email,
                        otp_hash=otp_hash_val,
                        expires_at=expires_at
                    )
                except Exception as create_err:
                    print(f"[OTP TOKEN CREATE ERROR] {create_err}")

                # Send OTP Email
                # Render free tier blocks SMTP → use Resend HTTP API as primary method
                subject = 'Your Verification Code - Eacyclic'
                plain_message = f'Hello,\n\nYour OTP verification code is: {otp_code}\n\nThis code is valid for 5 minutes. Do not share this code with anyone.'
                html_message = generate_otp_html_email(otp_code)

                email_sent = False
                email_error = None

                resend_api_key = getattr(settings, 'RESEND_API_KEY', '').strip()

                if resend_api_key:
                    # --- PRIMARY: Resend HTTP API (works on Render free tier) ---
                    try:
                        import resend
                        resend.api_key = resend_api_key
                        from_addr = getattr(settings, 'RESEND_FROM_EMAIL', 'Eacyclic <noreply@eacyclic.com>')
                        print(f"[OTP EMAIL] Sending via Resend API to {email} from {from_addr}")
                        params = {
                            "from": from_addr,
                            "to": [email],
                            "subject": subject,
                            "html": html_message,
                            "text": plain_message,
                        }
                        r = resend.Emails.send(params)
                        print(f"[OTP EMAIL] Resend response: {r}")
                        email_sent = True
                        print(f"[OTP EMAIL] Successfully sent to {email} via Resend")
                    except Exception as e:
                        import traceback
                        email_error = str(e)
                        print(f"[OTP EMAIL ERROR] Resend failed: {e}")
                        traceback.print_exc()
                else:
                    # --- FALLBACK: Django SMTP (works locally, blocked on Render free tier) ---
                    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@eacyclic.com'
                    try:
                        backend_used = getattr(settings, 'EMAIL_BACKEND', '')
                        print(f"[OTP EMAIL] Sending via SMTP to {email}, backend={backend_used}")
                        send_mail(
                            subject=subject,
                            message=plain_message,
                            from_email=from_email,
                            recipient_list=[email],
                            html_message=html_message,
                            fail_silently=False,
                        )
                        email_sent = True
                        print(f"[OTP EMAIL] Successfully sent to {email} via SMTP")
                    except Exception as e:
                        import traceback
                        email_error = str(e)
                        print(f"[OTP EMAIL ERROR] SMTP failed: {e}")
                        traceback.print_exc()

                if not email_sent:
                    print(f"=================================================")
                    print(f"[OTP FALLBACK] EMAIL FAILED — OTP FOR {email}: {otp_code}")
                    print(f"[OTP FALLBACK] Error: {email_error}")
                    print(f"=================================================")

                return Response({
                    'message': f'OTP code sent to {email}. Please check your inbox.',
                    'email': email,
                    'expires_in': 300
                }, status=status.HTTP_200_OK)


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

                token, _ = Token.objects.get_or_create(user=user)
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
                    token, _ = Token.objects.get_or_create(user=user)
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
                token = Token.objects.create(user=user)
                return Response({'token': token.key, 'user': UserSerializer(user).data})

            elif action == 'logout':
                auth_header = request.headers.get('Authorization', '')
                if auth_header.startswith('Token '):
                    token_key = auth_header.split(' ')[1]
                    Token.objects.filter(key=token_key).delete()
                if request.user.is_authenticated and hasattr(request.user, 'auth_token'):
                    try:
                        request.user.auth_token.delete()
                    except Exception:
                        pass
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
        password = request.data.get('password')

        if not username_or_email or not password:
            return Response({'error': 'Username/Email and password are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Case-insensitive lookup for username or email
        user_obj = User.objects.filter(
            Q(username__iexact=username_or_email) | Q(email__iexact=username_or_email)
        ).first()

        if user_obj:
            if user_obj.check_password(password):
                if not user_obj.is_active:
                    return Response({'error': 'Account is inactive'}, status=status.HTTP_403_FORBIDDEN)

                if not user_obj.is_staff:
                    user_obj.is_staff = True
                    user_obj.save()

                token, _ = Token.objects.get_or_create(user=user_obj)
                return Response({
                    'token': token.key,
                    'user': {
                        'username': user_obj.username,
                        'email': user_obj.email,
                        'role': 'superadmin' if user_obj.is_superuser else 'admin',
                        'loginTime': timezone.now().isoformat(),
                    }
                })

        # Standard Django authenticate fallback
        user = authenticate(username=username_or_email, password=password)
        if user and user.is_active:
            if not user.is_staff:
                user.is_staff = True
                user.save()
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': {
                    'username': user.username,
                    'email': user.email,
                    'role': 'superadmin' if user.is_superuser else 'admin',
                    'loginTime': timezone.now().isoformat(),
                }
            })

        return Response({'error': 'Invalid username/email or password'}, status=status.HTTP_401_UNAUTHORIZED)

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

        if len(new_password) < 6:
            return Response({'error': 'New password must be at least 6 characters long.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        # Re-get or create token to maintain session
        token, _ = Token.objects.get_or_create(user=user)

        return Response({'message': 'Password updated successfully!', 'token': token.key}, status=status.HTTP_200_OK)

# --- ANALYTICS ---
class AnalyticsViewSet(viewsets.ViewSet):
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

from django.http import JsonResponse
import os

def force_superuser_view(request):
    username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'superadmin')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'superadmin@123')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
    
    user = User.objects.filter(username=username).first()
    if user:
        user.set_password(password)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        return JsonResponse({'status': f'Success: Password updated for {username}'})
    else:
        User.objects.create_superuser(username=username, email=email, password=password)
        return JsonResponse({'status': f'Success: Superuser {username} created'})

