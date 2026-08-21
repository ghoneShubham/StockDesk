"""Day 15 — payment link UI, Razorpay webhook, reconciliation report."""

from __future__ import annotations

import logging

from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from apps.core.mixins import PermissionRequiredMixin
from apps.payments.services import (
    PaymentsAPIError,
    PaymentsConfigError,
    WebhookSignatureError,
    create_payment_link_for_sale,
    payment_reconciliation_rows,
    process_webhook,
)
from apps.sales.models import Sale

logger = logging.getLogger("stockdesk.payments")


class SendPaymentLinkView(PermissionRequiredMixin, View):
    """POST from invoice detail — create Razorpay Payment Link (test mode)."""

    permission_required = "payments.add_paymentlink"
    raise_exception = True

    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk)
        try:
            link = create_payment_link_for_sale(sale)
        except (PaymentsConfigError, PaymentsAPIError) as exc:
            messages.error(request, str(exc))
            return redirect("sales:sale_detail", pk=sale.pk)

        messages.success(
            request,
            f"Payment link created: {link.short_url}",
        )
        return redirect("sales:sale_detail", pk=sale.pk)


class PaymentReconcileReportView(PermissionRequiredMixin, TemplateView):
    """Owner-facing: gateway vs books disagreements (PRD §9)."""

    permission_required = "reports.view_financial_reports"
    template_name = "payments/reconcile.html"
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["issues"] = payment_reconciliation_rows()
        return ctx


@method_decorator(csrf_exempt, name="dispatch")
class RazorpayWebhookView(View):
    """
    Public webhook — unauthenticated. Treat as hostile until signature verifies.
    Always verify against the raw request body (PRD §9).
    """

    def post(self, request):
        raw = request.body
        signature = request.headers.get("X-Razorpay-Signature") or request.META.get(
            "HTTP_X_RAZORPAY_SIGNATURE"
        )
        try:
            result = process_webhook(raw, signature)
        except WebhookSignatureError as exc:
            logger.warning("Razorpay webhook rejected: %s", exc)
            return HttpResponseForbidden(str(exc))
        except Exception:
            logger.exception("Razorpay webhook processing error")
            return JsonResponse({"status": "error"}, status=500)

        return JsonResponse(result, status=200)

    def get(self, request):
        return HttpResponse("Razorpay webhook endpoint (POST only).", status=405)
