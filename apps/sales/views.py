from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View

from apps.core.mixins import PermissionRequiredMixin
from apps.inventory.models import StockMovement
from apps.masters.models import Product

from .forms import SaleForm, SaleItemFormSet, lines_from_formset
from .models import Sale, SaleItem
from .services import InsufficientStockError, SaleValidationError, create_sale_with_stock


class SaleListView(PermissionRequiredMixin, ListView):
    model = Sale
    permission_required = "sales.view_sale"
    template_name = "sales/list.html"
    context_object_name = "sales"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            Sale.objects.select_related("customer", "created_by")
            .annotate(line_count=Count("items"))
            .order_by("-sale_date", "-id")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            filters = (
                Q(invoice_no__icontains=q)
                | Q(customer__name__icontains=q)
                | Q(customer__phone__icontains=q)
            )
            qs = qs.filter(filters)
        return qs


class SaleDetailView(PermissionRequiredMixin, DetailView):
    """HTML invoice view. Printable PDF + S3 storage arrive on Day 8."""

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
        return ctx


class SaleCreateView(PermissionRequiredMixin, View):
    permission_required = "sales.add_sale"
    template_name = "sales/form.html"

    def get(self, request):
        return self._render(request, SaleForm(), SaleItemFormSet(instance=Sale()))

    def post(self, request):
        form = SaleForm(request.POST)
        formset = SaleItemFormSet(request.POST, instance=Sale())
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
                return self._render(request, form, formset)

            messages.success(
                request,
                f"Invoice {sale.invoice_no} saved — stock reduced for {sale.items.count()} line(s).",
            )
            return redirect(reverse("sales:sale_detail", kwargs={"pk": sale.pk}))

        messages.error(request, "Please fix the errors below.")
        return self._render(request, form, formset)

    def _render(self, request, form, formset):
        price_map = {
            str(p.id): str(p.sale_price)
            for p in Product.objects.filter(is_active=True, sellable=True).only("id", "sale_price")
        }
        return render(
            request,
            self.template_name,
            {"form": form, "formset": formset, "product_prices": price_map},
        )
