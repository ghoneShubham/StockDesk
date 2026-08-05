from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("", views.PurchaseListView.as_view(), name="purchase_list"),
    path("new/", views.PurchaseCreateView.as_view(), name="purchase_create"),
    path("<int:pk>/", views.PurchaseDetailView.as_view(), name="purchase_detail"),
]
