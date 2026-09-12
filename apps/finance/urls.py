from django.urls import path

from . import views

app_name = 'finance'

urlpatterns = [
    path('api/depense/', views.expense_create, name='expense_create'),
]