from django.core.management.base import BaseCommand
import sqlite3
import os
from django.conf import settings
from api.models import Order, OrderItem, Delivery

class Command(BaseCommand):
    help = "Syncs orders between Neon PostgreSQL and local SQLite"

    def handle(self, *args, **options):
        self.stdout.write("Syncing orders from active database to local SQLite...")

        sqlite_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
        if not os.path.exists(sqlite_path):
            self.stdout.write(self.style.ERROR(f"SQLite file not found at {sqlite_path}"))
            return

        orders = list(Order.objects.all().values())
        self.stdout.write(f"Found {len(orders)} total orders in active database.")

        conn = sqlite3.connect(sqlite_path)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(api_order)")
        sqlite_cols = [row[1] for row in cur.fetchall()]

        synced_count = 0
        for o in orders:
            filtered = {k: v for k, v in o.items() if k in sqlite_cols}
            for k, v in filtered.items():
                if hasattr(v, 'isoformat'):
                    filtered[k] = v.isoformat()
                elif hasattr(v, '__float__'):
                    filtered[k] = float(v)

            keys = list(filtered.keys())
            vals = list(filtered.values())
            placeholders = ', '.join(['?'] * len(keys))
            cols_str = ', '.join([f'"{k}"' for k in keys])
            cur.execute(f'INSERT OR REPLACE INTO api_order ({cols_str}) VALUES ({placeholders})', vals)
            synced_count += 1

        conn.commit()

        # Sync items
        items = list(OrderItem.objects.all().values())
        cur.execute("PRAGMA table_info(api_orderitem)")
        item_cols = [row[1] for row in cur.fetchall()]
        item_count = 0
        for itm in items:
            filtered = {k: v for k, v in itm.items() if k in item_cols}
            for k, v in filtered.items():
                if hasattr(v, '__float__'):
                    filtered[k] = float(v)

            keys = list(filtered.keys())
            vals = list(filtered.values())
            placeholders = ', '.join(['?'] * len(keys))
            cols_str = ', '.join([f'"{k}"' for k in keys])
            cur.execute(f'INSERT OR REPLACE INTO api_orderitem ({cols_str}) VALUES ({placeholders})', vals)
            item_count += 1

        conn.commit()
        conn.close()

        self.stdout.write(self.style.SUCCESS(
            f"Successfully synced {synced_count} orders and {item_count} items to local SQLite ({sqlite_path})!"
        ))

