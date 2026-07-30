from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView


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
    """Module G — owner/manager landing page. Populated fully once sales/inventory exist (Day 6+)."""

    template_name = "core/dashboard.html"
