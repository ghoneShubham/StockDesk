from django.views.generic import TemplateView

from apps.core.mixins import PermissionRequiredMixin


class SaleListView(PermissionRequiredMixin, TemplateView):
    """
    Sales / billing list — all three roles have sales.view_sale.
    Full billing UI arrives on Day 7 — Day 3 only proves the gate.
    """

    permission_required = "sales.view_sale"
    template_name = "sales/list.html"
