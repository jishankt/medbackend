
from django.urls import path
from .views import create_order, verify_payment

urlpatterns = [
    path('create-order/', create_order),
    path('verify/', verify_payment),
]
