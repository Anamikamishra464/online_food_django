from django.urls import path
from . import views
from .views import create_checkout_session, payment_success, payment_cancel

urlpatterns = [
    path('place_order/',views.place_order, name='place_order'),
    path('payments/',views.payments, name='payments'),
    path('order_complete/', views.order_complete, name='order_complete'),
    path('create-checkout-session/', create_checkout_session, name='create_checkout_session'),
    path('payment-success/', payment_success, name='success'),
    path('payment-cancel/', payment_cancel, name='cancel'),
   
]
