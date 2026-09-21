from django.urls import path

from . import views

app_name = 'finance'

urlpatterns = [
    path('dettes/', views.debts_page, name='debts'),
    path('operations/', views.operations_page, name='operations'),
    path('api/depense/', views.expense_create, name='expense_create'),
    path('api/dettes/payer/', views.debt_pay, name='debt_pay'),
    path('api/creances/decider/', views.creance_decide, name='creance_decide'),
    path('api/operations/annuler/', views.operation_cancel, name='operation_cancel'),
    path('api/operations/modifier/', views.operation_update, name='operation_update'),
]