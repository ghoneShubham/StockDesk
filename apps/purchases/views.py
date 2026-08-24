from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View

from apps.core.mixins import PermissionRequiredMixin
from apps.core.query import annotate_line_count
from apps.inventory.models import StockMovement
from apps.masters.models import Product

from .forms import PurchaseForm, PurchaseItemFormSet, lines_from_formset
from .models import Purchase, PurchaseItem
from .services import create_purchase_with_stock


class PurchaseListView(PermissionRequiredMixin, ListView):
    model = Purchase
    permission_required = "purchases.view_purchase"
    template_name = "purchases/list.html"
    context_object_name = "purchases"
    paginate_by = 25

    def get_queryset(self):
        qs = annotate_line_count(
            Purchase.objects.select_related("supplier", "created_by"),
            related_model=PurchaseItem,
            fk_field="purchase_id",
        ).order_by("-purchase_date", "-id")
        q = self.request.GET.get("q", "").strip()
        if q:
            filters = Q(supplier__name__icontains=q) | Q(supplier_invoice_no__icontains=q)
            if q.isdigit():
                filters |= Q(id=int(q))
            qs = qs.filter(filters)
        return qs


class PurchaseDetailView(PermissionRequiredMixin, DetailView):
    model = Purchase
    permission_required = "purchases.view_purchase"
    template_name = "purchases/detail.html"
    context_object_name = "purchase"

    def get_queryset(self):
        return Purchase.objects.select_related("supplier", "created_by").prefetch_related(
            Prefetch("items", queryset=PurchaseItem.objects.select_related("product"))
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stock_movements"] = (
            StockMovement.objects.filter(
                reference_type=StockMovement.ReferenceType.PURCHASE,
                reference_id=self.object.pk,
            )
            .select_related("product")
            .order_by("id")
        )
        return ctx


class PurchaseCreateView(PermissionRequiredMixin, View):
    permission_required = "purchases.add_purchase"
    template_name = "purchases/form.html"

    def _product_queryset(self):
        return Product.objects.filter(is_active=True).only(
            "id", "sku", "name", "purchase_price"
        ).order_by("sku")

    def get(self, request):
        products = self._product_queryset()
        formset = PurchaseItemFormSet(
            instance=Purchase(), form_kwargs={"products_qs": products}
        )
        return self._render(request, PurchaseForm(), formset, products)

    def post(self, request):
        products = self._product_queryset()
        form = PurchaseForm(request.POST)
        formset = PurchaseItemFormSet(
            request.POST, instance=Purchase(), form_kwargs={"products_qs": products}
        )
        if form.is_valid() and formset.is_valid():
            lines = lines_from_formset(formset)
            try:
                purchase = create_purchase_with_stock(
                    supplier=form.cleaned_data["supplier"],
                    purchase_date=form.cleaned_data["purchase_date"],
                    supplier_invoice_no=form.cleaned_data.get("supplier_invoice_no") or "",
                    lines=lines,
                    user=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return self._render(request, form, formset, products)

            messages.success(
                request,
                f"Purchase #{purchase.pk} ({purchase.supplier_invoice_no}) saved - stock increased for {len(lines)} line(s).",
            )
            return redirect(reverse("purchases:purchase_detail", kwargs={"pk": purchase.pk}))

        messages.error(request, "Please fix the errors below.")
        return self._render(request, form, formset, products)

    def _render(self, request, form, formset, products=None):
        if products is None:
            products = self._product_queryset()
        price_map = {str(p.id): str(p.purchase_price) for p in products}
        return render(
            request,
            self.template_name,
            {"form": form, "formset": formset, "product_prices": price_map},
        )
