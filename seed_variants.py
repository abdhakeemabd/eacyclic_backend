import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import Product

def seed_variants():
    updated = 0
    for p in Product.objects.all():
        name = p.name.lower()
        cat = p.category.lower()

        sizes = []
        colors = []

        if 'bed' in name or 'cot' in name:
            sizes = ['6.25 x 5 ft', '6.25 x 6 ft', '6.25 x 4 ft']
            colors = ['Akeshya Wood', 'Teak Wood', 'Walnut Finish']
        elif 'table' in name and 'chair' not in name:
            sizes = ['4-Seater (4.5 x 3 ft)', '6-Seater (6 x 3.5 ft)', '8-Seater (7.5 x 4 ft)']
            colors = ['Solid Teak', 'Akeshya Wood', 'Dark Walnut']
        elif 'chair' in name or 'stool' in name:
            sizes = ['Single Chair', 'Set of 2', 'Set of 4', 'Set of 6']
            colors = ['Solid Teak', 'Akeshya Wood', 'Dark Walnut']
        elif 'wardrobe' in name or 'cupboard' in name:
            sizes = ['2-Door', '3-Door', '4-Door']
            colors = ['Akeshya Wood', 'Teak Wood', 'Walnut Finish']
        elif 'furniture' in cat or 'wood' in name:
            sizes = ['Standard', 'Compact', 'Large']
            colors = ['Akeshya Wood', 'Teak Wood', 'Walnut Finish']
        elif 'fashion' in cat or 'dress' in name or 'shirt' in name or 'saree' in name or 'kurti' in name or 'salwar' in name:
            sizes = ['S', 'M', 'L', 'XL', 'XXL']
            colors = ['Red', 'Green', 'Blue', 'Violet', 'Orange', 'Black', 'White']
        elif 'jewel' in cat or 'ring' in name or 'bangle' in name:
            sizes = ['Size 12', 'Size 14', 'Size 16', 'Size 18', 'Size 20']
            colors = ['Panchaloha Gold', 'Antique Copper', 'Rose Gold']
        elif 'perfume' in cat or 'fragrance' in name:
            sizes = ['50 ml', '100 ml', '200 ml']
            colors = ['Eau de Parfum', 'Intense Oud', 'Fresh Citrus']
        elif 'grocery' in cat or 'podi' in name or 'spice' in name:
            sizes = ['100g', '250g', '500g', '1 Kg']
            colors = ['Original Traditional', 'Spicy Extra', 'Mild Classic']
        elif 'health' in cat or 'soap' in cat:
            sizes = ['Single Pack', 'Pack of 3 (Value)', 'Pack of 5 (Family)']
            colors = ['Classic Original', 'Herbal Gold', 'Aloe Fresh']
        else:
            sizes = ['Standard Edition', 'Deluxe Edition']
            colors = ['Classic', 'Special Edition']

        p.sizes = sizes
        p.colors = colors
        p.save()
        updated += 1
        print(f"Updated product [{p.id}] '{p.name}': sizes={sizes}, colors={colors}")

    print(f"\nSuccessfully seeded variants for all {updated} products in the database!")

if __name__ == '__main__':
    seed_variants()
