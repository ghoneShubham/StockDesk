"""
Day 10 — run EXPLAIN ANALYZE on the three hottest list/aggregate queries
against the seeded database and print timings + plans.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count, Sum

from apps.core.query import annotate_line_count, annotate_stock_qty
from apps.inventory.models import StockMovement
from apps.masters.models import Product
from apps.sales.models import Sale, SaleItem


class Command(BaseCommand):
    help = "EXPLAIN ANALYZE the three hottest Day-10 queries (product stock, sales list, stock history)."

    def handle(self, *args, **options):
        self.stdout.write("=== StockDesk Day 10 hot-query profile ===\n")

        # 1) Product list stock annotate (valuation-shaped)
        qs1 = annotate_stock_qty(
            Product.objects.filter(is_active=True).select_related("category")
        ).order_by("name")[:25]
        self._run("1) Product list stock annotate (page of 25)", qs1)

        # Stock valuation style aggregate across all products
        qs1b = annotate_stock_qty(Product.objects.filter(is_active=True)).values(
            "id", "sku", "purchase_price", "stock_qty"
        )
        self._run_sql(
            "1b) Stock valuation-shaped annotate (all active products)",
            str(qs1b.query),
        )

        # 2) Sales list with line_count
        qs2 = annotate_line_count(
            Sale.objects.select_related("customer", "created_by"),
            related_model=SaleItem,
            fk_field="sale_id",
        ).order_by("-sale_date", "-id")[:25]
        self._run("2) Sales list + line_count subquery (page of 25)", qs2)

        # Baseline JOIN Count for comparison note
        qs2_join = (
            Sale.objects.select_related("customer", "created_by")
            .annotate(line_count=Count("items"))
            .order_by("-sale_date", "-id")[:25]
        )
        self._run("2b) Sales list + JOIN Count(items) baseline (page of 25)", qs2_join)

        # 3) Stock history for busiest product
        busiest = (
            StockMovement.objects.values("product_id")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        if not busiest:
            self.stdout.write(self.style.WARNING("No stock movements — seed data first."))
            return

        product_id = busiest["product_id"]
        qs3 = (
            StockMovement.objects.filter(product_id=product_id)
            .select_related("created_by")
            .order_by("-created_at", "-id")[:50]
        )
        self._run(
            f"3) Stock history page (product_id={product_id}, {busiest['n']} moves, page of 50)",
            qs3,
        )

        stock_sum = StockMovement.objects.filter(product_id=product_id).aggregate(
            s=Sum("qty_delta")
        )
        self.stdout.write(f"\nCurrent stock for product {product_id}: {stock_sum['s']}")
        self.stdout.write(self.style.SUCCESS("\nDone. Copy plans into docs/PERFORMANCE.md."))

    def _run(self, title: str, queryset):
        sql, params = queryset.query.sql_with_params()
        self._run_sql(title, sql, params)

    def _run_sql(self, title: str, sql: str, params=None):
        self.stdout.write(self.style.HTTP_INFO(f"\n--- {title} ---"))
        explain = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {sql}"
        t0 = time.perf_counter()
        with connection.cursor() as cursor:
            cursor.execute(explain, params or [])
            plan = "\n".join(row[0] for row in cursor.fetchall())
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.stdout.write(plan)
        self.stdout.write(f"\n[wall time for EXPLAIN ANALYZE call: {elapsed_ms:.1f} ms]")
