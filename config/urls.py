from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("masters/", include("apps.masters.urls")),
    path("purchases/", include("apps.purchases.urls")),
    path("sales/", include("apps.sales.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("reports/", include("apps.reports.urls")),
    path("payments/", include("apps.payments.urls")),
    path("webhooks/razorpay/", include("apps.payments.webhook_urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

