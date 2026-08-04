"""
Seed a realistic StockDesk dataset for performance / report work (PRD §7.1).

Targets:
  - 30 suppliers, 500 products, 200 customers
  - 800 purchases (~4,000 purchase lines)
  - 3,000 sales (~50,000 sale lines) across ~18 months
  - Matching StockMovement rows for opening stock, purchases, and sales

Usage:
  python manage.py seed_demo_data
  python manage.py seed_demo_data --flush   # wipe business data first
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone
from faker import Faker

from apps.inventory.models import Adjustment, StockMovement
from apps.masters.models import Category, Customer, Product, Supplier
from apps.purchases.models import Purchase, PurchaseItem
from apps.sales.models import InvoiceSequence, Sale, SaleItem

User = get_user_model()
IST = ZoneInfo("Asia/Kolkata")

# PRD §7.1 targets
N_SUPPLIERS = 30
N_PRODUCTS = 500
N_CUSTOMERS = 200
N_PURCHASES = 800
N_PURCHASE_LINES = 4000
N_SALES = 3000
N_SALE_LINES = 50000
MONTHS_SPAN = 18

CATEGORIES = [
    "Grocery",
    "Beverages",
    "Snacks",
    "Personal Care",
    "Household",
    "Dairy",
    "Frozen",
    "Stationery",
    "Electronics Accessories",
    "Health",
    "Baby Care",
    "Pet Care",
]

UNITS = [c.value for c in Product.Unit]


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def financial_year_for(dt: datetime) -> str:
    """Indian FY label, e.g. 2025-04-01 -> '2025-26'."""
    year = dt.year
    if dt.month < 4:
        return f"{year - 1}-{str(year)[2:]}"
    return f"{year}-{str(year + 1)[2:]}"


class Command(BaseCommand):
    help = "Seed realistic demo data (PRD §7.1) for performance and report work."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing business data before seeding.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="RNG seed for reproducible data (default: 42).",
        )

    def handle(self, *args, **options):
        fake = Faker("en_IN")
        Faker.seed(options["seed"])
        random.seed(options["seed"])

        call_command("bootstrap_roles")
        call_command("create_role_users")
        owner = User.objects.get(username="owner")

        if options["flush"]:
            self.stdout.write("Flushing existing business data...")
            self._flush_business_data()
        elif Product.objects.exists() or Sale.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Business data already exists. Re-run with --flush to wipe and reseed, "
                    "or continue only if you intentionally want duplicates (command will abort)."
                )
            )
            self.stdout.write(self.style.ERROR("Aborted. Use --flush to replace existing data."))
            return

        started = timezone.now()
        self.stdout.write("Seeding masters...")
        categories, suppliers, customers, products = self._seed_masters(fake)

        end = timezone.now().astimezone(IST)
        start = end - timedelta(days=30 * MONTHS_SPAN)

        self.stdout.write("Seeding opening stock...")
        stock = self._seed_opening_stock(products, owner, start)

        self.stdout.write("Seeding purchases...")
        self._seed_purchases(fake, suppliers, products, owner, start, end, stock)

        self.stdout.write("Seeding sales (~50k lines — this takes a few minutes)...")
        self._seed_sales(fake, customers, products, owner, start, end, stock)

        elapsed = (timezone.now() - started).total_seconds()
        self._print_summary(elapsed)

    # ------------------------------------------------------------------ flush
    def _flush_business_data(self):
        with transaction.atomic():
            SaleItem.objects.all().delete()
            Sale.objects.all().delete()
            InvoiceSequence.objects.all().delete()
            PurchaseItem.objects.all().delete()
            Purchase.objects.all().delete()
            # Null the PROTECT FK before removing movements.
            Adjustment.objects.all().update(stock_movement=None)
            Adjustment.objects.all().delete()
            StockMovement.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            Supplier.objects.all().delete()
            Customer.objects.all().delete()

    # ---------------------------------------------------------------- masters
    def _seed_masters(self, fake: Faker):
        categories = [Category(name=name, is_active=True) for name in CATEGORIES]
        Category.objects.bulk_create(categories)
        categories = list(Category.objects.all())

        suppliers = []
        for i in range(N_SUPPLIERS):
            suppliers.append(
                Supplier(
                    name=fake.company()[:255],
                    phone=fake.numerify(text="9#########"),
                    gstin=fake.bothify(text="##?????####?#Z#", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ").upper()[:15],
                    address=fake.address().replace("\n", ", ")[:500],
                    is_active=True,
                )
            )
        Supplier.objects.bulk_create(suppliers)
        suppliers = list(Supplier.objects.all())

        customers = []
        used_phones: set[str] = set()
        for _ in range(N_CUSTOMERS):
            phone = fake.numerify(text="9#########")
            while phone in used_phones:
                phone = fake.numerify(text="9#########")
            used_phones.add(phone)
            customers.append(
                Customer(
                    name=fake.name()[:255],
                    phone=phone,
                    address=fake.address().replace("\n", ", ")[:500],
                )
            )
        Customer.objects.bulk_create(customers)
        customers = list(Customer.objects.all())

        products = []
        for i in range(N_PRODUCTS):
            purchase = money(random.uniform(10, 800))
            markup = Decimal(str(random.uniform(1.15, 1.75)))
            sale = money(purchase * markup)
            products.append(
                Product(
                    sku=f"SKU-{i + 1:04d}",
                    name=f"{fake.word().title()} {fake.word().title()} {random.choice(['Pack', 'Box', 'Bottle', 'Tin', 'Bag'])}",
                    category=random.choice(categories),
                    unit=random.choice(UNITS),
                    hsn_code=fake.numerify(text="####"),
                    purchase_price=purchase,
                    sale_price=sale,
                    reorder_level=random.randint(5, 40),
                    sellable=True,
                    is_active=True,
                )
            )
        Product.objects.bulk_create(products)
        products = list(Product.objects.select_related("category"))
        return categories, suppliers, customers, products

    # ---------------------------------------------------------- opening stock
    def _seed_opening_stock(self, products, owner, start_dt):
        stock: dict[int, Decimal] = {}
        adjustments = []
        for product in products:
            qty = Decimal(random.randint(150, 450))
            stock[product.id] = qty
            adjustments.append(
                Adjustment(
                    product=product,
                    qty_delta=qty,
                    reason=Adjustment.Reason.OPENING_STOCK,
                    notes="Demo opening stock",
                    created_by=owner,
                )
            )
        Adjustment.objects.bulk_create(adjustments)
        adjustments = list(Adjustment.objects.select_related("product").order_by("id"))

        movements = []
        for adj in adjustments:
            movements.append(
                StockMovement(
                    product_id=adj.product_id,
                    movement_type=StockMovement.MovementType.OPENING,
                    qty_delta=adj.qty_delta,
                    reference_type=StockMovement.ReferenceType.ADJUSTMENT,
                    reference_id=adj.id,
                    reason="Opening stock",
                    created_by=owner,
                    created_at=start_dt,
                )
            )
        StockMovement.objects.bulk_create(movements, batch_size=500)

        # Link adjustments to movements
        moves_by_ref = {
            m.reference_id: m
            for m in StockMovement.objects.filter(reference_type=StockMovement.ReferenceType.ADJUSTMENT)
        }
        for adj in adjustments:
            adj.stock_movement = moves_by_ref[adj.id]
        Adjustment.objects.bulk_update(adjustments, ["stock_movement"], batch_size=500)
        return stock

    # ------------------------------------------------------------- purchases
    def _seed_purchases(self, fake, suppliers, products, owner, start, end, stock):
        span_seconds = int((end - start).total_seconds())
        purchases = []
        for i in range(N_PURCHASES):
            when = start + timedelta(seconds=random.randint(0, span_seconds))
            purchases.append(
                Purchase(
                    supplier=random.choice(suppliers),
                    supplier_invoice_no=f"SIN-{i + 1:05d}",
                    purchase_date=when.date(),
                    total_amount=Decimal("0"),
                    created_by=owner,
                    created_at=when,
                )
            )
        Purchase.objects.bulk_create(purchases, batch_size=200)
        purchases = list(Purchase.objects.order_by("id"))

        # Distribute ~4000 lines across 800 purchases (~5 each, with variance).
        lines_per_purchase = self._distribute_counts(N_PURCHASES, N_PURCHASE_LINES, min_each=3, max_each=10)

        items = []
        movements = []
        totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

        for purchase, n_lines in zip(purchases, lines_per_purchase):
            chosen = random.sample(products, k=min(n_lines, len(products)))
            when = timezone.make_aware(
                datetime.combine(purchase.purchase_date, datetime.min.time()),
                IST,
            )
            for product in chosen:
                qty = Decimal(random.randint(10, 60))
                rate = product.purchase_price
                amount = money(qty * rate)
                items.append(
                    PurchaseItem(
                        purchase=purchase,
                        product=product,
                        qty=qty,
                        rate=rate,
                        amount=amount,
                    )
                )
                totals[purchase.id] += amount
                stock[product.id] = stock.get(product.id, Decimal("0")) + qty
                movements.append(
                    StockMovement(
                        product_id=product.id,
                        movement_type=StockMovement.MovementType.PURCHASE,
                        qty_delta=qty,
                        reference_type=StockMovement.ReferenceType.PURCHASE,
                        reference_id=purchase.id,
                        reason=f"Purchase {purchase.supplier_invoice_no}",
                        created_by=owner,
                        created_at=when,
                    )
                )

        PurchaseItem.objects.bulk_create(items, batch_size=1000)
        StockMovement.objects.bulk_create(movements, batch_size=1000)

        for purchase in purchases:
            purchase.total_amount = money(totals[purchase.id])
        Purchase.objects.bulk_update(purchases, ["total_amount"], batch_size=200)

        self.stdout.write(f"  Purchases: {len(purchases)}, lines: {len(items)}")

    # ----------------------------------------------------------------- sales
    def _seed_sales(self, fake, customers, products, owner, start, end, stock):
        span_seconds = int((end - start).total_seconds())
        lines_per_sale = self._distribute_counts(N_SALES, N_SALE_LINES, min_each=8, max_each=30)

        # Pre-generate sale headers with unique invoice numbers per FY.
        fy_counters: dict[str, int] = defaultdict(int)
        sales = []
        sale_meta = []  # (sale_index, when, n_lines)

        for i in range(N_SALES):
            when = start + timedelta(seconds=random.randint(0, span_seconds))
            fy = financial_year_for(when.astimezone(IST))
            fy_counters[fy] += 1
            invoice_no = f"INV-{fy}-{fy_counters[fy]:06d}"
            customer = random.choice(customers) if random.random() > 0.15 else None
            sales.append(
                Sale(
                    invoice_no=invoice_no,
                    customer=customer,
                    sale_date=when,
                    subtotal=Decimal("0"),
                    discount=Decimal("0"),
                    tax=Decimal("0"),
                    total_amount=Decimal("0"),
                    payment_status=random.choices(
                        [
                            Sale.PaymentStatus.PAID,
                            Sale.PaymentStatus.PENDING,
                            Sale.PaymentStatus.PARTIAL,
                        ],
                        weights=[70, 20, 10],
                    )[0],
                    created_by=owner,
                    created_at=when,
                )
            )
            sale_meta.append((i, when, lines_per_sale[i]))

        Sale.objects.bulk_create(sales, batch_size=300)
        sales = list(Sale.objects.order_by("id"))

        for fy, last in fy_counters.items():
            InvoiceSequence.objects.update_or_create(
                financial_year=fy,
                defaults={"last_number": last},
            )

        items: list[SaleItem] = []
        movements: list[StockMovement] = []
        sale_totals: dict[int, dict[str, Decimal]] = {}

        product_pool = products[:]
        total_lines_created = 0

        for sale, (_, when, n_lines) in zip(sales, sale_meta):
            random.shuffle(product_pool)
            subtotal = Decimal("0")
            lines_made = 0
            for product in product_pool:
                if lines_made >= n_lines:
                    break
                available = stock.get(product.id, Decimal("0"))
                if available < 1:
                    continue
                qty = Decimal(min(int(available), random.randint(1, 5)))
                if qty < 1:
                    continue
                rate = product.sale_price
                line_gross = money(qty * rate)
                discount = money(0)
                if random.random() < 0.12:
                    discount = money(min(line_gross * Decimal("0.05"), line_gross))
                amount = money(line_gross - discount)
                items.append(
                    SaleItem(
                        sale=sale,
                        product=product,
                        qty=qty,
                        rate=rate,
                        discount=discount,
                        amount=amount,
                    )
                )
                stock[product.id] = available - qty
                movements.append(
                    StockMovement(
                        product_id=product.id,
                        movement_type=StockMovement.MovementType.SALE,
                        qty_delta=-qty,
                        reference_type=StockMovement.ReferenceType.SALE,
                        reference_id=sale.id,
                        reason=f"Sale {sale.invoice_no}",
                        created_by=owner,
                        created_at=when,
                    )
                )
                subtotal += amount
                lines_made += 1
                total_lines_created += 1

            header_discount = money(0)
            if random.random() < 0.08 and subtotal > 0:
                header_discount = money(min(subtotal * Decimal("0.02"), Decimal("50")))
            tax = money((subtotal - header_discount) * Decimal("0.05"))
            total = money(subtotal - header_discount + tax)
            sale_totals[sale.id] = {
                "subtotal": money(subtotal),
                "discount": header_discount,
                "tax": tax,
                "total_amount": total,
            }

            if len(items) >= 2000:
                SaleItem.objects.bulk_create(items, batch_size=1000)
                items.clear()
            if len(movements) >= 2000:
                StockMovement.objects.bulk_create(movements, batch_size=1000)
                movements.clear()

        if items:
            SaleItem.objects.bulk_create(items, batch_size=1000)
        if movements:
            StockMovement.objects.bulk_create(movements, batch_size=1000)

        for sale in sales:
            t = sale_totals.get(sale.id)
            if not t:
                continue
            sale.subtotal = t["subtotal"]
            sale.discount = t["discount"]
            sale.tax = t["tax"]
            sale.total_amount = t["total_amount"]
        Sale.objects.bulk_update(
            sales, ["subtotal", "discount", "tax", "total_amount"], batch_size=300
        )

        # Drop empty sales (no stock left for lines) — rare with generous opening stock.
        empty_ids = [s.id for s in sales if sale_totals.get(s.id, {}).get("subtotal", 0) == 0]
        if empty_ids:
            Sale.objects.filter(id__in=empty_ids).delete()
            self.stdout.write(self.style.WARNING(f"  Removed {len(empty_ids)} empty sales (no stock)."))

        self.stdout.write(f"  Sales lines created: {total_lines_created}")

    # --------------------------------------------------------------- helpers
    def _distribute_counts(self, n_groups: int, total: int, min_each: int, max_each: int) -> list[int]:
        """Return a list of length n_groups summing to ~total."""
        counts = [min_each] * n_groups
        remaining = total - (min_each * n_groups)
        if remaining < 0:
            raise ValueError("total too small for min_each * n_groups")
        i = 0
        while remaining > 0:
            room = max_each - counts[i % n_groups]
            if room > 0:
                add = min(room, remaining, random.randint(1, max(1, room)))
                counts[i % n_groups] += add
                remaining -= add
            i += 1
            if i > total * 3:
                break
        return counts

    def _print_summary(self, elapsed: float):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM masters_supplier),
                  (SELECT COUNT(*) FROM masters_product),
                  (SELECT COUNT(*) FROM masters_customer),
                  (SELECT COUNT(*) FROM purchases_purchase),
                  (SELECT COUNT(*) FROM purchases_purchaseitem),
                  (SELECT COUNT(*) FROM sales_sale),
                  (SELECT COUNT(*) FROM sales_saleitem),
                  (SELECT COUNT(*) FROM inventory_stockmovement)
                """
            )
            (
                n_suppliers,
                n_products,
                n_customers,
                n_purchases,
                n_purchase_items,
                n_sales,
                n_sale_items,
                n_movements,
            ) = cursor.fetchone()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed complete"))
        self.stdout.write(f"  Suppliers:       {n_suppliers:>7}  (target {N_SUPPLIERS})")
        self.stdout.write(f"  Products:        {n_products:>7}  (target {N_PRODUCTS})")
        self.stdout.write(f"  Customers:       {n_customers:>7}  (target {N_CUSTOMERS})")
        self.stdout.write(f"  Purchases:       {n_purchases:>7}  (target {N_PURCHASES})")
        self.stdout.write(f"  Purchase lines:  {n_purchase_items:>7}  (target ~{N_PURCHASE_LINES})")
        self.stdout.write(f"  Sales:           {n_sales:>7}  (target {N_SALES})")
        self.stdout.write(f"  Sale lines:      {n_sale_items:>7}  (target ~{N_SALE_LINES})")
        self.stdout.write(f"  Stock movements: {n_movements:>7}")
        self.stdout.write(f"  Elapsed:         {elapsed:.1f}s")
