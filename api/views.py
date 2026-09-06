from rest_framework import viewsets, views, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta

from .models import Product, Order, Contact, UserProfile, Cart, CartItem, Delivery
from .serializers import (ProductSerializer, OrderSerializer, ContactSerializer,
                          UserSerializer, CartSerializer, CartItemSerializer, DeliverySerializer)

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

# --- AUTH & USER PROFILE ---
class AuthView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request, action=None):
        if action == 'login':
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
            if request.user.is_authenticated:
                request.user.auth_token.delete()
                return Response({'status': 'Logged out'})
            return Response({'error': 'Not logged in'}, status=400)

class UserProfileView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        user = request.user
        user.first_name = request.data.get('first_name', user.first_name)
        user.last_name = request.data.get('last_name', user.last_name)
        user.save()
        
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.phone = request.data.get('phone', profile.phone)
        profile.address = request.data.get('address', profile.address)
        profile.save()
        
        return Response(UserSerializer(user).data)

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
