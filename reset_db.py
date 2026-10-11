import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

def reset_database():
    with connection.cursor() as cursor:
        db_engine = connection.settings_dict.get('ENGINE', '')
        if 'postgresql' in db_engine:
            print("[DATABASE RESET] Dropping and recreating public schema in PostgreSQL...")
            cursor.execute("DROP SCHEMA public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")
            cursor.execute("GRANT ALL ON SCHEMA public TO public;")
            print("[DATABASE RESET] PostgreSQL public schema successfully recreated fresh.")
        else:
            print(f"[DATABASE RESET] Current database engine: {db_engine}")

if __name__ == '__main__':
    reset_database()
