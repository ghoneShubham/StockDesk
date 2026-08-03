from django.views.generic import TemplateView

from apps.core.mixins import PermissionRequiredMixin


class ReportsIndexView(PermissionRequiredMixin, TemplateView):
    """
    Operational reports landing page.
    Owner + Store Manager have reports.view_operational_reports; Cashier does not.
    Full report implementations arrive on Days 11–12 — Day 3 only proves the gate.
    """

    permission_required = "reports.view_operational_reports"
    template_name = "reports/index.html"


class FinancialReportsView(PermissionRequiredMixin, TemplateView):
    """
    Financial reports (margin, valuation, P&L) — Owner only per PRD Section 3.
    Cashier/Manager editing this URL by hand must get HTTP 403.
    """

    permission_required = "reports.view_financial_reports"
    template_name = "reports/financial.html"
