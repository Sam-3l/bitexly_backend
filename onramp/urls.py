from django.urls import path
from . import views

urlpatterns = [
    path('quote/', views.get_onramp_quote, name='onramp_quote'),
    path('payment-methods/', views.get_onramp_payment_methods, name='onramp_payment_methods'),
    path('generate-url/', views.generate_onramp_url, name='onramp_generate_url'),
]