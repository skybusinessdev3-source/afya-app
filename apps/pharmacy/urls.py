from django.urls import path

from . import views

app_name = 'pharmacy'

urlpatterns = [
    path('', views.pharmacy_sale, name='sale'),
    path('api/recherche-produits/', views.product_search, name='product_search'),
    path('api/vente/', views.sale_create, name='sale_create'),
    path('api/nouveau-produit/', views.product_create, name='product_create'),
    path('produits/', views.products_page, name='products'),
    path('api/produit/<int:pk>/modifier/', views.api_product_update, name='api_product_update'),
    path('api/produit/<int:pk>/stock/', views.api_stock_add, name='api_stock_add'),
    path('api/produit/<int:pk>/basculer/', views.api_product_toggle, name='api_product_toggle'),
]