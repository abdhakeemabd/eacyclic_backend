from rest_framework import permissions

class IsAdminUserOnly(permissions.BasePermission):
    """
    Allows access only to authenticated administrators (staff or superusers).
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_staff or request.user.is_superuser)
        )


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Allows read-only access (GET, HEAD, OPTIONS) to anyone, 
    but restricts write actions (POST, PUT, PATCH, DELETE) strictly to administrators.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_staff or request.user.is_superuser)
        )


class IsAdminOrContactSubmit(permissions.BasePermission):
    """
    Allows public users to submit contact inquiries (POST),
    while restricting all management operations (viewing, deleting, status updates) to admins.
    """
    def has_permission(self, request, view):
        if request.method == 'POST' or getattr(view, 'action', None) == 'create':
            return True
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_staff or request.user.is_superuser)
        )


class IsAdminOrOrderPlacement(permissions.BasePermission):
    """
    Allows anyone to place an order (POST),
    but restricts listing all orders, updating statuses, and deletion strictly to admins.
    """
    def has_permission(self, request, view):
        if getattr(view, 'action', None) == 'create':
            return True
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_staff or request.user.is_superuser)
        )
