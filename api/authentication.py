from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from rest_framework.authentication import TokenAuthentication
from rest_framework import exceptions

TOKEN_EXPIRE_HOURS = getattr(settings, 'TOKEN_EXPIRE_HOURS', 24)

class ExpiringTokenAuthentication(TokenAuthentication):
    """
    Production-grade Token Authentication with a strict 24-hour expiration window.
    Any token older than 24 hours is automatically revoked from the database and rejected.
    """
    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            token = model.objects.select_related('user').get(key=key)
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid or revoked access token.')

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('User account is deactivated.')

        # Enforce 24-hour token lifetime
        now = timezone.now()
        if token.created < (now - timedelta(hours=TOKEN_EXPIRE_HOURS)):
            token.delete()  # Invalidate stale token from the database
            raise exceptions.AuthenticationFailed('Session has expired after 24 hours. Please log in again.')

        return (token.user, token)
