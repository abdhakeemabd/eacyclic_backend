import os
import django
from decouple import config

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()

# Read superuser credentials strictly from the server environment (Zero static defaults)
username = config('DJANGO_SUPERUSER_USERNAME', default=os.environ.get('DJANGO_SUPERUSER_USERNAME', '')).strip()
password = config('DJANGO_SUPERUSER_PASSWORD', default=os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')).strip()
email = config('DJANGO_SUPERUSER_EMAIL', default=os.environ.get('DJANGO_SUPERUSER_EMAIL', '')).strip()

if username and password:
    user, created = User.objects.get_or_create(username=username, defaults={'email': email})
    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True
    user.is_active = True
    if email:
        user.email = email
    user.save()

    # Invalidate all preexisting tokens on update/creation
    Token.objects.filter(user=user).delete()

    action = "created" if created else "updated"
    print(f"[SECURITY] Superuser '{username}' {action} successfully from server environment variables.")
else:
    print("[SECURITY] No static credentials found. Provide DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD as secure server environment variables.")
