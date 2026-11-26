from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Delivery, Order, Product


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_SYNC_FOR_TESTS=True,
    ADMIN_NOTIFICATION_EMAIL='owner@eacyclic.com',
)
class StoreWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.product = Product.objects.create(
            name='Aakeshya Dining Chair',
            description='Solid wood dining chair',
            price=1450,
            old_price=1700,
            category='Furniture',
            stock=10,
            isActive=True,
            freeShipping=True,
        )

    def test_health_endpoint(self):
        resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'ok')

    def test_otp_login_sends_email_and_returns_token(self):
        resp = self.client.post('/api/auth/send-otp', {'email': 'buyer@example.com'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('buyer@example.com', mail.outbox[0].to)

    def test_guest_order_creation_requires_authentication(self):
        payload = {
            'customer_name': 'Guest User',
            'customer_email': 'guest@example.com',
            'customer_phone': '9876543210',
            'shipping_address': 'Kozhikode, Kerala',
            'subtotal': 1450,
            'total': 1450,
            'items': [{'product_id': self.product.id, 'product_name': self.product.name, 'quantity': 1, 'price': 1450}],
        }
        resp = self.client.post('/api/orders', payload, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_order_creation_sends_customer_and_admin_emails(self):
        customer = User.objects.create_user('customer1', 'customer@example.com', 'Pass12345!')
        self.client.force_authenticate(user=customer)
        payload = {
            'customer_name': 'Hakeem Customer',
            'customer_email': 'customer@example.com',
            'customer_phone': '9876543210',
            'shipping_address': 'Green Villa, Kozhikode, Kerala - 673001, India',
            'subtotal': 1450,
            'shipping_cost': 0,
            'tax': 0,
            'total': 1450,
            'payment_method': 'Cash on Delivery',
            'items': [
                {
                    'product_id': self.product.id,
                    'product_name': self.product.name,
                    'selected_size': 'Single Chair',
                    'selected_color': 'Solid Teak',
                    'quantity': 1,
                    'price': 1450,
                }
            ],
        }
        resp = self.client.post('/api/orders', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        order_id = resp.data['id']
        self.assertTrue(Order.objects.filter(id=order_id).exists())
        self.assertTrue(Delivery.objects.filter(order_id=order_id).exists())

        # Both customer confirmation and admin alert should be sent
        self.assertEqual(len(mail.outbox), 2)
        recipients = [addr for msg in mail.outbox for addr in msg.to]
        self.assertIn('customer@example.com', recipients)
        self.assertIn('owner@eacyclic.com', recipients)
        self.assertIn(f'#{order_id}', mail.outbox[0].subject)

    def test_other_user_cannot_cancel_someone_elses_order(self):
        owner = User.objects.create_user('owner1', 'owner1@example.com', 'Pass12345!')
        stranger = User.objects.create_user('stranger', 'stranger@example.com', 'Pass12345!')
        order = Order.objects.create(
            id=5555555555,
            user=owner,
            customer_name='Owner One',
            customer_email='owner1@example.com',
            customer_phone='9876543210',
            shipping_address='Kozhikode, Kerala',
            subtotal=1450,
            total=1450,
        )
        self.client.force_authenticate(user=stranger)
        resp = self.client.post(f'/api/orders/{order.id}/cancel', {}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_status_update_sends_customer_email(self):
        admin = User.objects.create_superuser('adminuser', 'admin@eacyclic.com', 'StrongPass123!')
        order = Order.objects.create(
            id=1234567890,
            customer_name='Buyer',
            customer_email='buyer@example.com',
            customer_phone='9876543210',
            shipping_address='Kochi, Kerala',
            subtotal=1450,
            total=1450,
        )
        Delivery.objects.create(order=order, tracking_number='EAC1234567890AB')

        self.client.force_authenticate(user=admin)
        resp = self.client.patch(f'/api/orders/{order.id}/status', {'status': 'shipped'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Shipped', mail.outbox[0].subject)
        self.assertIn('buyer@example.com', mail.outbox[0].to)

    def test_reorder_populates_user_cart(self):
        user = User.objects.create_user('repeatbuyer', 'repeat@example.com', 'Pass12345!')
        order = Order.objects.create(
            id=9876543210,
            user=user,
            customer_name='Repeat Buyer',
            customer_email='repeat@example.com',
            customer_phone='9876543210',
            shipping_address='Malappuram, Kerala',
            subtotal=2900,
            total=2900,
        )
        order.items.create(
            product_id=self.product.id,
            product_name=self.product.name,
            selected_size='Single Chair',
            selected_color='Solid Teak',
            quantity=2,
            price=1450,
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(f'/api/orders/{order.id}/reorder', {}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['added_count'], 1)
        self.assertEqual(len(resp.data['cart']['items']), 1)
        self.assertEqual(resp.data['cart']['items'][0]['quantity'], 2)
