from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.http import JsonResponse
from django.views.generic import TemplateView

from apps.reports import queries as report_queries


def health_check(request):
    """
    `/health/` — checked externally every 5 minutes (Section 12.1).
    Verifies both the app process and the database connection are alive.
    """
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_ok = False

    status = 200 if db_ok else 503
    return JsonResponse({"status": "ok" if db_ok else "error", "database": db_ok}, status=status)


class DashboardView(LoginRequiredMixin, TemplateView):
    """Module G — today's sales, month sales, low stock, pending payments, top 5."""

    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        metrics = report_queries.dashboard_metrics()
        ctx.update(metrics)
        user = self.request.user
        ctx["can_see_low_stock"] = user.has_perm("reports.view_operational_reports")
        ctx["can_see_pending_payments"] = user.has_perm("sales.view_sale")
        return ctx
