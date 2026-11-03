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

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['product_id', 'product_name', 'selected_size', 'selected_color', 'quantity', 'price']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = '__all__'

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        return order

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = '__all__'

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'age', 'gender']

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    name = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'name', 'phone', 'address', 'age', 'gender', 'profile']

    def get_name(self, obj):
        return obj.first_name or obj.username

    def get_phone(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.phone if profile else ''

    def get_address(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.address if profile else ''

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

class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = '__all__'
