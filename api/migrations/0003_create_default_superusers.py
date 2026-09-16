from django.db import migrations
from django.contrib.auth.hashers import make_password


def create_superusers(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    hashed_password = make_password('admin123')

    # 1. Ensure 'admin' user exists with superuser privileges and password 'admin123'
    admin_user, _ = User.objects.get_or_create(username='admin')
    admin_user.email = 'admin@eacyclic.com'
    admin_user.password = hashed_password
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.is_active = True
    admin_user.save()

    # 2. Ensure 'admin_nisam' user exists with superuser privileges and password 'admin123'
    nisam_user, _ = User.objects.get_or_create(username='admin_nisam')
    nisam_user.email = 'admin_nisam@eacyclic.com'
    nisam_user.password = hashed_password
    nisam_user.is_staff = True
    nisam_user.is_superuser = True
    nisam_user.is_active = True
    nisam_user.save()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_create_missing_tables'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_superusers, reverse_code=migrations.RunPython.noop),
    ]
