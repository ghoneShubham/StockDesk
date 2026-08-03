from django.views.generic import TemplateView

from apps.core.mixins import PermissionRequiredMixin


class PurchaseListView(PermissionRequiredMixin, TemplateView):
    """
    Purchases are Owner + Store Manager only (PRD Section 3).
    Cashier must receive 403 if they hit this URL directly.
    Full formset UI arrives on Day 6 — Day 3 only proves the gate.
    """

    permission_required = "purchases.view_purchase"
    template_name = "purchases/list.html"
