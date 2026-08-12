from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View

from apps.core.mixins import PermissionRequiredMixin
from apps.masters.models import Product

from .forms import AdjustmentForm
from .models import Adjustment, StockMovement
from .services import AdjustmentError, apply_adjustment, current_stock


class AdjustmentListView(PermissionRequiredMixin, ListView):
    model = Adjustment
    permission_required = "inventory.view_adjustment"
    template_name = "inventory/adjustment_list.html"
    context_object_name = "adjustments"
    paginate_by = 25

    def get_queryset(self):
        qs = Adjustment.objects.select_related("product", "created_by", "stock_movement").order_by(
            "-created_at", "-id"
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(product__sku__icontains=q)
                | Q(product__name__icontains=q)
                | Q(notes__icontains=q)
                | Q(reason__icontains=q)
            )
        return qs


class AdjustmentDetailView(PermissionRequiredMixin, DetailView):
    model = Adjustment
    permission_required = "inventory.view_adjustment"
    template_name = "inventory/adjustment_detail.html"
    context_object_name = "adjustment"

    def get_queryset(self):
        return Adjustment.objects.select_related("product", "created_by", "stock_movement")


class AdjustmentCreateView(PermissionRequiredMixin, View):
    permission_required = "inventory.add_adjustment"
    template_name = "inventory/adjustment_form.html"

    def get(self, request):
        initial = {}
        product_id = request.GET.get("product")
        if product_id:
            initial["product"] = product_id
        return render(request, self.template_name, {"form": AdjustmentForm(initial=initial)})

    def post(self, request):
        form = AdjustmentForm(request.POST)
        if form.is_valid():
            try:
                adjustment = apply_adjustment(
                    product=form.cleaned_data["product"],
                    qty_delta=form.cleaned_data["qty_delta"],
                    reason=form.cleaned_data["reason"],
                    notes=form.cleaned_data.get("notes") or "",
                    user=request.user,
                )
            except AdjustmentError as exc:
                messages.error(request, str(exc))
                return render(request, self.template_name, {"form": form})

            messages.success(
                request,
                f"Adjustment #{adjustment.pk} saved for {adjustment.product.sku} "
                f"({adjustment.qty_delta:+}).",
            )
            return redirect(reverse("inventory:adjustment_detail", kwargs={"pk": adjustment.pk}))

        messages.error(request, "Please fix the errors below.")
        return render(request, self.template_name, {"form": form})


class ProductStockHistoryView(PermissionRequiredMixin, DetailView):
    """
    Per-product stock ledger with running balance (PRD R1).
    Paginated newest-first; balance reconstructed without loading the full ledger.
    """

    model = Product
    permission_required = "inventory.view_stockmovement"
    template_name = "inventory/stock_history.html"
    context_object_name = "product"
    pk_url_kwarg = "pk"
    paginate_by = 50

    def get_queryset(self):
        return Product.objects.select_related("category")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        movements_qs = (
            StockMovement.objects.filter(product=self.object)
            .select_related("created_by")
            .order_by("-created_at", "-id")
        )
        paginator = Paginator(movements_qs, self.paginate_by)
        page_obj = paginator.get_page(self.request.GET.get("page"))

        stock_now = current_stock(self.object.pk)
        # Balance after the newest movement on this page =
        # current stock minus sum of movements newer than the page start.
        if page_obj.object_list:
            first = page_obj.object_list[0]
            newer_sum = (
                StockMovement.objects.filter(product=self.object)
                .filter(
                    Q(created_at__gt=first.created_at)
                    | Q(created_at=first.created_at, id__gt=first.id)
                )
                .aggregate(s=Sum("qty_delta"))["s"]
                or Decimal("0.00")
            )
            running = stock_now - newer_sum
        else:
            running = stock_now

        rows = []
        for m in page_obj.object_list:
            rows.append({"movement": m, "balance": running})
            running -= m.qty_delta

        ctx["history_rows"] = rows
        ctx["page_obj"] = page_obj
        ctx["current_stock"] = stock_now
        ctx["can_adjust"] = self.request.user.has_perm("inventory.add_adjustment")
        return ctx
