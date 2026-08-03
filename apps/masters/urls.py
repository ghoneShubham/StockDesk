from django.urls import path

from . import views

app_name = "masters"

urlpatterns = [
    path("", views.MastersIndexView.as_view(), name="index"),
    # Categories
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/add/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categories/<int:pk>/deactivate/", views.CategoryDeactivateView.as_view(), name="category_deactivate"),
    # Products
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/add/", views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("products/<int:pk>/edit/", views.ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/deactivate/", views.ProductDeactivateView.as_view(), name="product_deactivate"),
    # Suppliers
    path("suppliers/", views.SupplierListView.as_view(), name="supplier_list"),
    path("suppliers/add/", views.SupplierCreateView.as_view(), name="supplier_create"),
    path("suppliers/<int:pk>/edit/", views.SupplierUpdateView.as_view(), name="supplier_update"),
    path("suppliers/<int:pk>/deactivate/", views.SupplierDeactivateView.as_view(), name="supplier_deactivate"),
    # Customers
    path("customers/", views.CustomerListView.as_view(), name="customer_list"),
    path("customers/add/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("customers/<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("customers/<int:pk>/delete/", views.CustomerDeleteView.as_view(), name="customer_delete"),
]
