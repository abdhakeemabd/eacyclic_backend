from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Product, Order, OrderItem, Contact, UserProfile, Cart, CartItem, Delivery

class ProductSerializer(serializers.ModelSerializer):
    oldPrice = serializers.DecimalField(max_digits=10, decimal_places=2, source='old_price', required=False, allow_null=True)

    class Meta:
        model = Product
        fields = '__all__'

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        val = data.get('oldPrice') if data.get('oldPrice') is not None else data.get('old_price')
        if val is not None:
            data['old_price'] = val
            data['oldPrice'] = val
        return super().to_internal_value(data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        val = ret.get('old_price') if ret.get('old_price') is not None else ret.get('oldPrice')
        ret['old_price'] = val
        ret['oldPrice'] = val
        return ret

class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = '__all__'

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['product_id', 'product_name', 'product_image', 'selected_size', 'selected_color', 'quantity', 'price']

class OrderSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    items = OrderItemSerializer(many=True)
    delivery = DeliverySerializer(read_only=True)

    class Meta:
        model = Order
        fields = '__all__'

    def validate_items(self, value):
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one order item is required.")
        return value

    def create(self, validated_data):
        import secrets
        import time
        import random
        from django.db import transaction
        from django.utils import timezone
        from datetime import timedelta

        items_data = validated_data.pop('items')
        
        # Ensure unique order id if not provided
        if not validated_data.get('id'):
            validated_data['id'] = int(time.time()) * 1000 + random.randint(100, 999)

        # Link user if request context has authenticated user
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['user'] = request.user
            if not validated_data.get('customer_email'):
                validated_data['customer_email'] = request.user.email

        with transaction.atomic():
            try:
                order = Order.objects.create(**validated_data)
            except Exception as e:
                # Resilient fallback if table is missing optional columns
                err_str = str(e).lower()
                if 'user_id' in err_str or 'user' in err_str:
                    validated_data.pop('user', None)
                if 'payment_method' in err_str:
                    validated_data.pop('payment_method', None)
                if 'payment_status' in err_str:
                    validated_data.pop('payment_status', None)
                order = Order.objects.create(**validated_data)

            for item_data in items_data:
                try:
                    OrderItem.objects.create(order=order, **item_data)
                except Exception as e:
                    if 'product_image' in str(e).lower():
                        item_data.pop('product_image', None)
                        OrderItem.objects.create(order=order, **item_data)
                    else:
                        raise e

            # Auto-create tracking / delivery record for the order
            try:
                tracking_num = f"EAC{order.id}{secrets.token_hex(2).upper()}"
                Delivery.objects.create(
                    order=order,
                    status='processing',
                    tracking_number=tracking_num,
                    carrier='BlueDart / Delhivery Express',
                    estimated_delivery=timezone.now() + timedelta(days=4)
                )
            except Exception:
                pass

        return order

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = '__all__'

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'saved_addresses', 'age', 'gender']

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    name = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    saved_addresses = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'name', 'phone', 'address', 'saved_addresses', 'age', 'gender', 'profile']

    def get_name(self, obj):
        return obj.first_name or obj.username

    def get_phone(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.phone if profile else ''

    def get_address(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.address if profile else ''

    def get_saved_addresses(self, obj):
        profile = getattr(obj, 'profile', None)
        if not profile:
            return []
        addrs = getattr(profile, 'saved_addresses', None)
        if addrs and isinstance(addrs, list) and len(addrs) > 0:
            return addrs
        if profile.address:
            return [{
                'id': 1,
                'name': obj.first_name or obj.username or 'Default',
                'phone': profile.phone or '',
                'type': 'HOME',
                'houseName': profile.address,
                'area': '',
                'city': '',
                'district': '',
                'state': 'Kerala',
                'pincode': '',
                'country': 'India',
                'isDefault': True
            }]
        return []

    def get_age(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.age if profile else None

    def get_gender(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.gender if profile else ''

class CartItemSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    
    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_details', 'selected_size', 'selected_color', 'quantity']

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'created_at']
