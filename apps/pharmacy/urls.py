from django.urls import path

from . import views

app_name = 'pharmacy'

urlpatterns = [
    path('', views.pharmacy_sale, name='sale'),
    path('api/recherche-produits/', views.product_search, name='product_search'),
    path('api/vente/', views.sale_create, name='sale_create'),
    path('api/nouveau-produit/', views.product_create, name='product_create'),
]