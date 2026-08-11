from django.contrib import messages
from django.db.models import Count, Prefetch
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View

from apps.core.mixins import PermissionRequiredMixin
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
        from django.db.models import Q

        qs = (
            Purchase.objects.select_related("supplier", "created_by")
            .annotate(line_count=Count("items"))
            .order_by("-purchase_date", "-id")
        )
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

    def get(self, request):
        return self._render(request, PurchaseForm(), PurchaseItemFormSet(instance=Purchase()))

    def post(self, request):
        form = PurchaseForm(request.POST)
        formset = PurchaseItemFormSet(request.POST, instance=Purchase())
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
                return self._render(request, form, formset)

            messages.success(
                request,
                f"Purchase #{purchase.pk} saved — stock increased for {purchase.items.count()} line(s).",
            )
            return redirect(reverse("purchases:purchase_detail", kwargs={"pk": purchase.pk}))

        messages.error(request, "Please fix the errors below.")
        return self._render(request, form, formset)

    def _render(self, request, form, formset):
        price_map = {
            str(p.id): str(p.purchase_price)
            for p in Product.objects.filter(is_active=True).only("id", "purchase_price")
        }
        return render(
            request,
            self.template_name,
            {"form": form, "formset": formset, "product_prices": price_map},
        )
