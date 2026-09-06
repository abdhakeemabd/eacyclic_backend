import os
import django
import json
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import Product, Order, OrderItem, Contact

def load_data():
    with open(r'c:\Users\hakeempc\Music\hkm\hkm\personal\e-commerce\db.json', 'r') as f:
        data = json.load(f)

    print("Loading Products...")
    for p in data.get('products', []):
        Product.objects.get_or_create(
            id=p['id'],
            defaults={
                'name': p['name'],
                'description': p['description'],
                'price': p['price'],
                'category': p['category'],
                'stock': p['stock'],
                'image_url': p['image_url'],
                'discount': p.get('discount', 0),
                'created_at': p.get('created_at', datetime.now().isoformat())
            }
        )

    print("Loading Orders...")
    for o in data.get('orders', []):
        order, created = Order.objects.get_or_create(
            id=o['id'],
            defaults={
                'customer_name': o['customer_name'],
                'customer_email': o['customer_email'],
                'customer_phone': o['customer_phone'],
                'shipping_address': o['shipping_address'],
                'status': o['status'],
                'total': o['total'],
                'subtotal': o['subtotal'],
                'shipping_cost': o['shipping_cost'],
                'tax': o['tax'],
                'created_at': o.get('created_at', datetime.now().isoformat())
            }
        )
        if created:
            for item in o.get('items', []):
                OrderItem.objects.create(
                    order=order,
                    product_id=item['product_id'],
                    product_name=item['product_name'],
                    quantity=item['quantity'],
                    price=item['price']
                )

    print("Loading Contacts...")
    for c in data.get('contacts', []):
        Contact.objects.get_or_create(
            id=c['id'],
            defaults={
                'name': c['name'],
                'email': c['email'],
                'phone': c['phone'],
                'subject': c['subject'],
                'message': c['message'],
                'is_read': c.get('is_read', False),
                'created_at': c.get('created_at', datetime.now().isoformat())
            }
        )
    print("Data loaded successfully!")

if __name__ == '__main__':
    load_data()
