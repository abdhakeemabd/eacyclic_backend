"""
Dynamic Product Sitemap Generator

Endpoint: GET /api/sitemap-products/
Returns a sitemap XML file containing all active products.

This allows Google to discover and index every individual product page
on Eacyclic — the same way Amazon and Flipkart work.

Add to urls.py:
    from .sitemap import sitemap_products_view
    path('api/sitemap-products/', sitemap_products_view, name='sitemap_products'),
"""
from django.http import HttpResponse
from .models import Product
from datetime import datetime

SITE_URL = 'https://eacyclic.com'

def sitemap_products_view(request):
    products = Product.objects.filter(isActive=True).values('id', 'name', 'created_at')

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]

    for product in products:
        lastmod = product['created_at'].strftime('%Y-%m-%d') if product['created_at'] else datetime.now().strftime('%Y-%m-%d')
        xml_lines += [
            '  <url>',
            f'    <loc>{SITE_URL}/product-view/{product["id"]}</loc>',
            f'    <lastmod>{lastmod}</lastmod>',
            '    <changefreq>weekly</changefreq>',
            '    <priority>0.8</priority>',
            '  </url>',
        ]

    xml_lines.append('</urlset>')

    return HttpResponse('\n'.join(xml_lines), content_type='application/xml')
