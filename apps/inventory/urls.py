from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("adjustments/", views.AdjustmentListView.as_view(), name="adjustment_list"),
    path("adjustments/new/", views.AdjustmentCreateView.as_view(), name="adjustment_create"),
    path("adjustments/<int:pk>/", views.AdjustmentDetailView.as_view(), name="adjustment_detail"),
    path(
        "products/<int:pk>/history/",
        views.ProductStockHistoryView.as_view(),
        name="product_stock_history",
    ),
]
