import json
import urllib.request
import urllib.error

url = 'http://localhost:8000/api/orders'
data = {
    'id': 999,
    'created_at': '2026-09-06T12:00:00Z',
    'customer_name': 'Test',
    'customer_email': '',
    'customer_phone': '1234567890',
    'shipping_address': 'Address',
    'subtotal': 100.0,
    'shipping_cost': 0.0,
    'tax': 0.0,
    'total': 100.0,
    'status': 'pending',
    'items': [{
        'product_id': None,
        'product_name': 'Test Item',
        'quantity': 1,
        'price': 100.0
    }]
}

req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})

try:
    with urllib.request.urlopen(req) as response:
        print('Status:', response.status)
        print('Response:', response.read().decode())
except urllib.error.HTTPError as e:
    print('Status:', e.code)
    print('Error:', e.read().decode())
