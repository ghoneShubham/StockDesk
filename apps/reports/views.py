"""
Reports Set 1 views — date filters + CSV export (PRD Day 11 / Module E).

Permissions (Section 3):
- Operational reports → reports.view_operational_reports (Owner + Store Manager)
- Financial reports → reports.view_financial_reports (Owner only)
"""

from django.views.generic import TemplateView

from apps.core.mixins import PermissionRequiredMixin

from . import queries
from .csv_export import csv_response
from .forms import DateRangeForm


class ReportsIndexView(PermissionRequiredMixin, TemplateView):
    permission_required = "reports.view_operational_reports"
    template_name = "reports/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["operational_reports"] = [
            {"name": "Daily sales", "url_name": "reports:daily_sales", "desc": "Totals per day, including zero-sales days"},
            {"name": "Top products", "url_name": "reports:top_products", "desc": "Top 10 by revenue and by quantity"},
            {"name": "Low stock", "url_name": "reports:low_stock", "desc": "At or below reorder level"},
            {"name": "Inactive customers", "url_name": "reports:inactive_customers", "desc": "No purchase in the last 90 days"},
            {"name": "Supplier purchases", "url_name": "reports:supplier_purchases", "desc": "Totals and distinct products"},
            {"name": "Dead stock", "url_name": "reports:dead_stock", "desc": "On hand, no movement in 60 days"},
            {"name": "Invoice integrity", "url_name": "reports:integrity", "desc": "Line totals that disagree with headers"},
        ]
        return ctx


class FinancialReportsView(PermissionRequiredMixin, TemplateView):
    permission_required = "reports.view_financial_reports"
    template_name = "reports/financial.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["financial_reports"] = [
            {"name": "Stock valuation", "url_name": "reports:stock_valuation", "desc": "qty × purchase price"},
            {"name": "Profit margin", "url_name": "reports:profit_margin", "desc": "Per product, divide-by-zero safe"},
        ]
        return ctx


class _DateRangeReportView(PermissionRequiredMixin, TemplateView):
    """Shared date-range GET form + optional ?export=csv."""

    permission_required = "reports.view_operational_reports"
    default_days = 30
    csv_filename = "report.csv"

    def get_form(self):
        if self.request.GET.get("date_from") or self.request.GET.get("date_to"):
            return DateRangeForm(self.request.GET, default_days=self.default_days)
        return DateRangeForm(default_days=self.default_days)

    def build_rows(self, date_from, date_to):
        raise NotImplementedError

    def csv_headers(self):
        raise NotImplementedError

    def csv_rows(self, rows):
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_bound and not form.is_valid():
            date_from = form.fields["date_from"].initial
            date_to = form.fields["date_to"].initial
            rows = []
            allow_export = False
        elif form.is_valid():
            date_from = form.cleaned_data["date_from"]
            date_to = form.cleaned_data["date_to"]
            rows = self.build_rows(date_from, date_to)
            allow_export = True
        else:
            # Unbound — use defaults and run the report.
            date_from = form.fields["date_from"].initial
            date_to = form.fields["date_to"].initial
            rows = self.build_rows(date_from, date_to)
            allow_export = True

        if allow_export and request.GET.get("export") == "csv":
            return csv_response(self.csv_filename, self.csv_headers(), self.csv_rows(rows))

        self.form = form
        self.date_from = date_from
        self.date_to = date_to
        self.rows = rows
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = self.form
        ctx["date_from"] = self.date_from
        ctx["date_to"] = self.date_to
        ctx["rows"] = self.rows
        return ctx


class DailySalesReportView(_DateRangeReportView):
    template_name = "reports/daily_sales.html"
    csv_filename = "daily_sales.csv"
    default_days = 30

    def build_rows(self, date_from, date_to):
        return queries.daily_sales_totals(date_from, date_to)

    def csv_headers(self):
        return ["Date", "Invoices", "Total sales"]

    def csv_rows(self, rows):
        for r in rows:
            yield [r["day"].isoformat(), r["invoice_count"], r["total_sales"]]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["grand_total"] = sum((r["total_sales"] for r in self.rows), queries.ZERO)
        ctx["grand_invoices"] = sum((r["invoice_count"] for r in self.rows), 0)
        return ctx


class TopProductsReportView(_DateRangeReportView):
    template_name = "reports/top_products.html"
    csv_filename = "top_products.csv"

    def build_rows(self, date_from, date_to):
        return {
            "by_revenue": queries.top_products(date_from, date_to, by="revenue"),
            "by_quantity": queries.top_products(date_from, date_to, by="quantity"),
        }

    def csv_headers(self):
        return ["Rank type", "SKU", "Name", "Qty sold", "Revenue"]

    def csv_rows(self, rows):
        for rank_type, key in (("revenue", "by_revenue"), ("quantity", "by_quantity")):
            for r in rows[key]:
                yield [rank_type, r["product__sku"], r["product__name"], r["qty_sold"], r["revenue"]]


class LowStockReportView(PermissionRequiredMixin, TemplateView):
    permission_required = "reports.view_operational_reports"
    template_name = "reports/low_stock.html"

    def get(self, request, *args, **kwargs):
        self.rows = queries.low_stock_products()
        if request.GET.get("export") == "csv":
            return csv_response(
                "low_stock.csv",
                ["SKU", "Name", "Category", "Stock", "Reorder level"],
                (
                    [p.sku, p.name, p.category.name, p.stock_qty, p.reorder_level]
                    for p in self.rows
                ),
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rows"] = self.rows
        return ctx


class InactiveCustomersReportView(PermissionRequiredMixin, TemplateView):
    permission_required = "reports.view_operational_reports"
    template_name = "reports/inactive_customers.html"

    def get(self, request, *args, **kwargs):
        self.rows = queries.inactive_customers(days=90)
        if request.GET.get("export") == "csv":
            return csv_response(
                "inactive_customers.csv",
                ["Name", "Phone", "Last purchase"],
                (
                    [
                        r["name"],
                        r["phone"],
                        r["last_purchase_at"].isoformat() if r["last_purchase_at"] else "",
                    ]
                    for r in self.rows
                ),
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rows"] = self.rows
        ctx["days"] = 90
        return ctx


class SupplierPurchasesReportView(_DateRangeReportView):
    template_name = "reports/supplier_purchases.html"
    csv_filename = "supplier_purchases.csv"
    default_days = 90

    def build_rows(self, date_from, date_to):
        return queries.supplier_purchase_totals(date_from, date_to)

    def csv_headers(self):
        return ["Supplier", "Purchases", "Distinct products", "Total amount"]

    def csv_rows(self, rows):
        for r in rows:
            yield [r["supplier__name"], r["purchase_count"], r["distinct_products"], r["total_amount"]]


class DeadStockReportView(PermissionRequiredMixin, TemplateView):
    permission_required = "reports.view_operational_reports"
    template_name = "reports/dead_stock.html"

    def get(self, request, *args, **kwargs):
        self.rows = queries.dead_stock(days=60)
        if request.GET.get("export") == "csv":
            return csv_response(
                "dead_stock.csv",
                ["SKU", "Name", "Category", "Stock qty"],
                ([p.sku, p.name, p.category.name, p.stock_qty] for p in self.rows),
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rows"] = self.rows
        ctx["days"] = 60
        return ctx


class IntegrityReportView(PermissionRequiredMixin, TemplateView):
    permission_required = "reports.view_operational_reports"
    template_name = "reports/integrity.html"

    def get(self, request, *args, **kwargs):
        self.rows = queries.invoice_integrity_issues()
        if request.GET.get("export") == "csv":
            return csv_response(
                "invoice_integrity.csv",
                [
                    "Invoice",
                    "Sale date",
                    "Subtotal",
                    "Lines sum",
                    "Discount",
                    "Tax",
                    "Total",
                    "Expected total",
                ],
                (
                    [
                        r["invoice_no"],
                        r["sale_date"].isoformat(),
                        r["subtotal"],
                        r["lines_sum"],
                        r["discount"],
                        r["tax"],
                        r["total_amount"],
                        r["expected_total"],
                    ]
                    for r in self.rows
                ),
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rows"] = self.rows
        return ctx


class StockValuationReportView(PermissionRequiredMixin, TemplateView):
    permission_required = "reports.view_financial_reports"
    template_name = "reports/stock_valuation.html"

    def get(self, request, *args, **kwargs):
        self.data = queries.stock_valuation()
        if request.GET.get("export") == "csv":
            return csv_response(
                "stock_valuation.csv",
                ["SKU", "Name", "Category", "Qty", "Purchase price", "Value"],
                (
                    [r["sku"], r["name"], r["category"], r["stock_qty"], r["purchase_price"], r["value"]]
                    for r in self.data["lines"]
                ),
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(self.data)
        return ctx


class ProfitMarginReportView(_DateRangeReportView):
    permission_required = "reports.view_financial_reports"
    template_name = "reports/profit_margin.html"
    csv_filename = "profit_margin.csv"
    default_days = 30

    def build_rows(self, date_from, date_to):
        return queries.profit_margin_by_product(date_from, date_to)

    def csv_headers(self):
        return ["SKU", "Name", "Qty sold", "Revenue", "Cost", "Profit", "Margin %"]

    def csv_rows(self, rows):
        for r in rows:
            yield [
                r["sku"],
                r["name"],
                r["qty_sold"],
                r["revenue"],
                r["cost"],
                r["profit"],
                "" if r["margin_pct"] is None else r["margin_pct"],
            ]
