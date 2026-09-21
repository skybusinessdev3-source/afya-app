from django.urls import path

from . import views

app_name = 'finance'

urlpatterns = [
    path('dettes/', views.debts_page, name='debts'),
    path('api/depense/', views.expense_create, name='expense_create'),
    path('api/dettes/payer/', views.debt_pay, name='debt_pay'),
]