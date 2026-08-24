import logging

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View

from apps.core.mixins import PermissionRequiredMixin
from apps.core.query import annotate_line_count
from apps.inventory.models import StockMovement
from apps.masters.models import Product
from apps.payments.models import PaymentLink

from .forms import SaleForm, SaleItemFormSet, lines_from_formset
from .models import Sale, SaleItem
from .pdf import ensure_invoice_pdf
from .services import InsufficientStockError, SaleValidationError, create_sale_with_stock, peek_next_invoice_no

logger = logging.getLogger("stockdesk.sales")

UNPAID_FILTER = "unpaid"
UNPAID_STATUSES = (Sale.PaymentStatus.PENDING, Sale.PaymentStatus.PARTIAL)


class SaleListView(PermissionRequiredMixin, ListView):
    model = Sale
    permission_required = "sales.view_sale"
    template_name = "sales/list.html"
    context_object_name = "sales"
    paginate_by = 25

    def get_queryset(self):
        qs = annotate_line_count(
            Sale.objects.select_related("customer", "created_by"),
            related_model=SaleItem,
            fk_field="sale_id",
        ).order_by("-sale_date", "-id")

        q = self.request.GET.get("q", "").strip()
        if q:
            filters = (
                Q(invoice_no__icontains=q)
                | Q(customer__name__icontains=q)
                | Q(customer__phone__icontains=q)
            )
            # Allow typing payment status words, e.g. "pending", "paid", "partial"
            q_lower = q.casefold()
            status_hits = [
                code
                for code, label in Sale.PaymentStatus.choices
                if q_lower in code.casefold() or q_lower in label.casefold()
            ]
            if status_hits:
                filters |= Q(payment_status__in=status_hits)
            qs = qs.filter(filters)

        payment_status = self.request.GET.get("payment_status", "").strip()
        valid_statuses = {c for c, _ in Sale.PaymentStatus.choices}
        if payment_status == UNPAID_FILTER:
            qs = qs.filter(payment_status__in=UNPAID_STATUSES)
        elif payment_status in valid_statuses:
            qs = qs.filter(payment_status=payment_status)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["payment_status_filter"] = self.request.GET.get("payment_status", "")
        ctx["payment_status_choices"] = Sale.PaymentStatus.choices
        ctx["unpaid_filter"] = UNPAID_FILTER
        ctx["is_pending_payments"] = ctx["payment_status_filter"] == UNPAID_FILTER
        return ctx


class SaleDetailView(PermissionRequiredMixin, DetailView):
    """HTML invoice detail with PDF download (Day 8)."""

    model = Sale
    permission_required = "sales.view_sale"
    template_name = "sales/detail.html"
    context_object_name = "sale"

    def get_queryset(self):
        return Sale.objects.select_related("customer", "created_by").prefetch_related(
            Prefetch("items", queryset=SaleItem.objects.select_related("product"))
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stock_movements"] = (
            StockMovement.objects.filter(
                reference_type=StockMovement.ReferenceType.SALE,
                reference_id=self.object.pk,
            )
            .select_related("product")
            .order_by("id")
        )
        ctx["payment_links"] = (
            PaymentLink.objects.filter(sale=self.object).order_by("-created_at")[:10]
        )
        ctx["can_send_payment_link"] = self.request.user.has_perm("payments.add_paymentlink")
        return ctx


class SaleInvoicePDFView(PermissionRequiredMixin, View):
    """
    Stream the stored invoice PDF. Generates + stores it on first request
    (default storage = local media in dev, S3 in production).
    """

    permission_required = "sales.view_sale"

    def get(self, request, pk):
        sale = get_object_or_404(
            Sale.objects.select_related("customer", "created_by").prefetch_related("items__product"),
            pk=pk,
        )
        try:
            sale = ensure_invoice_pdf(sale)
        except Exception:
            logger.exception("Failed to build PDF for sale %s", sale.invoice_no)
            messages.error(request, "Could not generate the invoice PDF. Please try again.")
            return redirect(reverse("sales:sale_detail", kwargs={"pk": sale.pk}))

        if not sale.pdf:
            raise Http404("Invoice PDF not available.")

        response = FileResponse(
            sale.pdf.open("rb"),
            content_type="application/pdf",
            as_attachment=False,
            filename=f"{sale.invoice_no}.pdf",
        )
        return response


class SaleCreateView(PermissionRequiredMixin, View):
    permission_required = "sales.add_sale"
    template_name = "sales/form.html"

    def _product_queryset(self):
        return Product.objects.filter(is_active=True, sellable=True).only(
            "id", "sku", "name", "sale_price"
        ).order_by("name")

    def get(self, request):
        products = self._product_queryset()
        formset = SaleItemFormSet(instance=Sale(), form_kwargs={"products_qs": products})
        return self._render(request, SaleForm(), formset, products)

    def post(self, request):
        products = self._product_queryset()
        form = SaleForm(request.POST)
        formset = SaleItemFormSet(request.POST, instance=Sale(), form_kwargs={"products_qs": products})
        if form.is_valid() and formset.is_valid():
            lines = lines_from_formset(formset)
            try:
                sale = create_sale_with_stock(
                    customer=form.cleaned_data.get("customer"),
                    sale_date=form.cleaned_data["sale_date"],
                    lines=lines,
                    header_discount=form.cleaned_data.get("discount") or 0,
                    tax=form.cleaned_data.get("tax") or 0,
                    payment_status=form.cleaned_data.get("payment_status") or Sale.PaymentStatus.PENDING,
                    user=request.user,
                )
            except (InsufficientStockError, SaleValidationError, ValueError) as exc:
                messages.error(request, str(exc))
                return self._render(request, form, formset, products)

            try:
                ensure_invoice_pdf(sale)
            except Exception:
                logger.exception("Sale %s saved but PDF generation failed", sale.invoice_no)
                messages.warning(
                    request,
                    f"Invoice {sale.invoice_no} saved, but the PDF could not be generated yet. "
                    "Open the invoice and use Download PDF to retry.",
                )
            else:
                messages.success(
                    request,
                    f"Invoice {sale.invoice_no} saved - stock reduced for {len(lines)} line(s).",
                )
            return redirect(reverse("sales:sale_detail", kwargs={"pk": sale.pk}))

        messages.error(request, "Please fix the errors below.")
        return self._render(request, form, formset, products)

    def _render(self, request, form, formset, products=None):
        if products is None:
            products = self._product_queryset()
        price_map = {str(p.id): str(p.sale_price) for p in products}
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "formset": formset,
                "product_prices": price_map,
                "preview_invoice_no": peek_next_invoice_no(),
            },
        )
