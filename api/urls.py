from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (ProductViewSet, OrderViewSet, ContactViewSet, DeliveryViewSet, 
                    CartViewSet, AuthView, UserProfileView, AnalyticsViewSet)

router = DefaultRouter(trailing_slash=False)
router.register(r'products', ProductViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'contacts', ContactViewSet)
router.register(r'deliveries', DeliveryViewSet)
router.register(r'analytics', AnalyticsViewSet, basename='analytics')

urlpatterns = [
    path('', include(router.urls)),
    
    # Cart custom paths
    path('cart', CartViewSet.as_view({'get': 'list'})),
    path('cart/add', CartViewSet.as_view({'post': 'add'})),
    path('cart/clear', CartViewSet.as_view({'delete': 'clear'})),
    path('cart/<int:pk>', CartViewSet.as_view({'put': 'update_item', 'delete': 'destroy_item'})),
    
    # Auth paths
    path('auth/<str:action>', AuthView.as_view()),
    
    # User Profile path
    path('user/profile', UserProfileView.as_view()),
]
