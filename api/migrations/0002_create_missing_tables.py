from django.db import migrations


FIX_ALL_TABLES_AND_COLUMNS_SQL = """
-- 1. Ensure api_product table exists
CREATE TABLE IF NOT EXISTS api_product (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    category VARCHAR(100) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    image_url TEXT,
    discount NUMERIC(5, 2) NOT NULL DEFAULT 0,
    "isActive" BOOLEAN NOT NULL DEFAULT TRUE,
    "freeShipping" BOOLEAN NOT NULL DEFAULT TRUE,
    gallery JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Ensure api_contact table exists
CREATE TABLE IF NOT EXISTS api_contact (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(254) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Ensure api_order table exists and has all required columns
CREATE TABLE IF NOT EXISTS api_order (
    id INTEGER PRIMARY KEY,
    customer_name VARCHAR(255) NOT NULL DEFAULT '',
    customer_email VARCHAR(254),
    customer_phone VARCHAR(20) NOT NULL DEFAULT '',
    shipping_address TEXT NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    total NUMERIC(10, 2) NOT NULL DEFAULT 0,
    subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0,
    shipping_cost NUMERIC(10, 2) NOT NULL DEFAULT 0,
    tax NUMERIC(10, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE api_order ADD COLUMN IF NOT EXISTS customer_name VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS customer_email VARCHAR(254);
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS customer_phone VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS shipping_address TEXT NOT NULL DEFAULT '';
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'pending';
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS total NUMERIC(10, 2) NOT NULL DEFAULT 0;
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0;
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS shipping_cost NUMERIC(10, 2) NOT NULL DEFAULT 0;
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS tax NUMERIC(10, 2) NOT NULL DEFAULT 0;
ALTER TABLE api_order ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 4. Ensure api_orderitem table exists and has required columns
CREATE TABLE IF NOT EXISTS api_orderitem (
    id BIGSERIAL PRIMARY KEY,
    product_id INTEGER,
    product_name VARCHAR(255) NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 1,
    price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    order_id INTEGER NOT NULL REFERENCES api_order(id) ON DELETE CASCADE
);

ALTER TABLE api_orderitem ADD COLUMN IF NOT EXISTS product_id INTEGER;
ALTER TABLE api_orderitem ADD COLUMN IF NOT EXISTS product_name VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE api_orderitem ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1;
ALTER TABLE api_orderitem ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2) NOT NULL DEFAULT 0;

-- 5. Ensure api_userprofile table exists
CREATE TABLE IF NOT EXISTS api_userprofile (
    id BIGSERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    user_id INTEGER NOT NULL UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE
);

-- 6. Ensure api_cart table exists
CREATE TABLE IF NOT EXISTS api_cart (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id INTEGER NOT NULL UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE
);

-- 7. Ensure api_cartitem table exists
CREATE TABLE IF NOT EXISTS api_cartitem (
    id BIGSERIAL PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 1,
    cart_id BIGINT NOT NULL REFERENCES api_cart(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES api_product(id) ON DELETE CASCADE
);

-- 8. Ensure api_delivery table exists
CREATE TABLE IF NOT EXISTS api_delivery (
    id BIGSERIAL PRIMARY KEY,
    status VARCHAR(50) NOT NULL DEFAULT 'processing',
    tracking_number VARCHAR(100) NOT NULL DEFAULT '',
    driver_name VARCHAR(100) NOT NULL DEFAULT '',
    driver_phone VARCHAR(20) NOT NULL DEFAULT '',
    estimated_delivery TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    order_id INTEGER NOT NULL UNIQUE REFERENCES api_order(id) ON DELETE CASCADE
);

-- 9. Safely drop NOT NULL constraints from all legacy non-PK columns on all api_* tables in PostgreSQL
DO $$ 
DECLARE 
    tbl RECORD;
    r RECORD;
BEGIN 
    FOR tbl IN 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name LIKE 'api_%'
    LOOP
        FOR r IN 
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = tbl.table_name 
              AND column_name != 'id'
        LOOP 
            EXECUTE format('ALTER TABLE %I ALTER COLUMN %I DROP NOT NULL;', tbl.table_name, r.column_name);
        END LOOP;
    END LOOP;
END $$;
"""


def run_postgres_sql(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(FIX_ALL_TABLES_AND_COLUMNS_SQL)

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(
            code=run_postgres_sql,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

