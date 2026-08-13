from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportsIndexView.as_view(), name="index"),
    path("financial/", views.FinancialReportsView.as_view(), name="financial"),
    # Set 1 — operational
    path("daily-sales/", views.DailySalesReportView.as_view(), name="daily_sales"),
    path("top-products/", views.TopProductsReportView.as_view(), name="top_products"),
    path("low-stock/", views.LowStockReportView.as_view(), name="low_stock"),
    path("inactive-customers/", views.InactiveCustomersReportView.as_view(), name="inactive_customers"),
    path("supplier-purchases/", views.SupplierPurchasesReportView.as_view(), name="supplier_purchases"),
    path("dead-stock/", views.DeadStockReportView.as_view(), name="dead_stock"),
    path("integrity/", views.IntegrityReportView.as_view(), name="integrity"),
    # Set 1 — financial (Owner)
    path("stock-valuation/", views.StockValuationReportView.as_view(), name="stock_valuation"),
    path("profit-margin/", views.ProfitMarginReportView.as_view(), name="profit_margin"),
]
