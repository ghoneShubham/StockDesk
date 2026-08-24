from decimal import Decimal

from django.contrib import messages
from django.db.models import ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from apps.core.mixins import PermissionRequiredMixin
from apps.core.query import annotate_stock_qty
from apps.inventory.models import StockMovement

from .forms import CategoryForm, CustomerForm, ProductForm, SupplierForm
from .models import Category, Customer, Product, Supplier


class MastersIndexView(PermissionRequiredMixin, TemplateView):
    permission_required = "masters.view_product"
    template_name = "masters/index.html"


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
class CategoryListView(PermissionRequiredMixin, ListView):
    model = Category
    permission_required = "masters.view_category"
    template_name = "masters/category_list.html"
    context_object_name = "categories"
    paginate_by = 25

    def get_queryset(self):
        qs = Category.objects.all()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs


class CategoryCreateView(PermissionRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    permission_required = "masters.add_category"
    template_name = "masters/category_form.html"
    success_url = reverse_lazy("masters:category_list")

    def form_valid(self, form):
        messages.success(self.request, f"Category “{form.instance.name}” created.")
        return super().form_valid(form)


class CategoryUpdateView(PermissionRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    permission_required = "masters.change_category"
    template_name = "masters/category_form.html"
    success_url = reverse_lazy("masters:category_list")

    def form_valid(self, form):
        messages.success(self.request, f"Category “{form.instance.name}” updated.")
        return super().form_valid(form)


class CategoryDeactivateView(PermissionRequiredMixin, View):
    permission_required = "masters.change_category"

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        category.is_active = False
        category.save(update_fields=["is_active", "updated_at"])
        messages.success(request, f"Category “{category.name}” deactivated.")
        return redirect("masters:category_list")


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
class ProductListView(PermissionRequiredMixin, ListView):
    model = Product
    permission_required = "masters.view_product"
    template_name = "masters/product_list.html"
    context_object_name = "products"
    paginate_by = 25

    def get_queryset(self):
        qs = annotate_stock_qty(Product.objects.select_related("category")).order_by("name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(sku__icontains=q) | Q(name__icontains=q) | Q(hsn_code__icontains=q))
        status = self.request.GET.get("status", "active")
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_view_purchase_price"] = self.request.user.has_perm("masters.view_purchase_price")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["status"] = self.request.GET.get("status", "active")
        return ctx


class ProductDetailView(PermissionRequiredMixin, DetailView):
    model = Product
    permission_required = "masters.view_product"
    template_name = "masters/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return annotate_stock_qty(Product.objects.select_related("category"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_view_purchase_price"] = self.request.user.has_perm("masters.view_purchase_price")
        stock = getattr(self.object, "stock_qty", None)
        if stock is None:
            stock = (
                StockMovement.objects.filter(product=self.object).aggregate(s=Sum("qty_delta"))["s"]
                or Decimal("0.00")
            )
        ctx["stock_qty"] = stock
        return ctx


class ProductCreateView(PermissionRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    permission_required = "masters.add_product"
    template_name = "masters/product_form.html"
    success_url = reverse_lazy("masters:product_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Product “{self.object.sku} — {self.object.name}” created.")
        return response


class ProductUpdateView(PermissionRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    permission_required = "masters.change_product"
    template_name = "masters/product_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("masters:product_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, f"Product “{form.instance.name}” updated.")
        return super().form_valid(form)


class ProductDeactivateView(PermissionRequiredMixin, View):
    """
    Soft-delete: products with stock movement history must not be hard-deleted
    (PRD test #15). Deactivating keeps history explainable.
    """

    permission_required = "masters.change_product"

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        product.is_active = False
        product.sellable = False
        product.save(update_fields=["is_active", "sellable", "updated_at"])
        messages.success(request, f"Product “{product.name}” deactivated (soft-deleted).")
        return redirect("masters:product_list")


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------
class SupplierListView(PermissionRequiredMixin, ListView):
    model = Supplier
    permission_required = "masters.view_supplier"
    template_name = "masters/supplier_list.html"
    context_object_name = "suppliers"
    paginate_by = 25

    def get_queryset(self):
        qs = Supplier.objects.all()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q))
        return qs


class SupplierCreateView(PermissionRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    permission_required = "masters.add_supplier"
    template_name = "masters/supplier_form.html"
    success_url = reverse_lazy("masters:supplier_list")

    def form_valid(self, form):
        messages.success(self.request, f"Supplier “{form.instance.name}” created.")
        return super().form_valid(form)


class SupplierUpdateView(PermissionRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    permission_required = "masters.change_supplier"
    template_name = "masters/supplier_form.html"
    success_url = reverse_lazy("masters:supplier_list")

    def form_valid(self, form):
        messages.success(self.request, f"Supplier “{form.instance.name}” updated.")
        return super().form_valid(form)


class SupplierDeactivateView(PermissionRequiredMixin, View):
    permission_required = "masters.change_supplier"

    def post(self, request, pk):
        supplier = get_object_or_404(Supplier, pk=pk)
        supplier.is_active = False
        supplier.save(update_fields=["is_active", "updated_at"])
        messages.success(request, f"Supplier “{supplier.name}” deactivated.")
        return redirect("masters:supplier_list")


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
class CustomerListView(PermissionRequiredMixin, ListView):
    model = Customer
    permission_required = "masters.view_customer"
    template_name = "masters/customer_list.html"
    context_object_name = "customers"
    paginate_by = 25

    def get_queryset(self):
        qs = Customer.objects.all()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q))
        return qs


class CustomerCreateView(PermissionRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    permission_required = "masters.add_customer"
    template_name = "masters/customer_form.html"
    success_url = reverse_lazy("masters:customer_list")

    def form_valid(self, form):
        messages.success(self.request, f"Customer “{form.instance.name}” created.")
        return super().form_valid(form)


class CustomerUpdateView(PermissionRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    permission_required = "masters.change_customer"
    template_name = "masters/customer_form.html"
    success_url = reverse_lazy("masters:customer_list")

    def form_valid(self, form):
        messages.success(self.request, f"Customer “{form.instance.name}” updated.")
        return super().form_valid(form)


class CustomerDeleteView(PermissionRequiredMixin, View):
    permission_required = "masters.delete_customer"

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        if customer.sales.exists():
            messages.error(
                request,
                f"Cannot delete “{customer.name}” — they have sales history. Keep the record for audit.",
            )
            return redirect("masters:customer_list")
        try:
            name = customer.name
            customer.delete()
            messages.success(request, f"Customer “{name}” deleted.")
        except ProtectedError:
            messages.error(request, "Cannot delete this customer because related records exist.")
        return redirect("masters:customer_list")
