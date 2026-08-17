"""
Day 7 concurrency proof (PRD R2 / R3).

Fires two concurrent sales against the last unit of a product.
Expected: one succeeds, one fails cleanly with InsufficientStockError;
final stock is 0; no negative stock.

Usage (from project root, venv active):

    python scripts/concurrency_proof.py

Optional env:
    DJANGO_SETTINGS_MODULE=config.settings.dev  (default)
"""

from __future__ import annotations

import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import AbstractUser, Group  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.models import Sum  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.core.permissions import CASHIER, OWNER  # noqa: E402
from apps.inventory.models import StockMovement  # noqa: E402
from apps.masters.models import Category, Product, Supplier  # noqa: E402
from apps.purchases.services import create_purchase_with_stock  # noqa: E402
from apps.sales.models import Sale  # noqa: E402
from apps.sales.services import InsufficientStockError, create_sale_with_stock  # noqa: E402

UserModel = get_user_model()


def stock_of(product: Product) -> Decimal:
    total = StockMovement.objects.filter(product=product).aggregate(s=Sum("qty_delta"))["s"]
    return total or Decimal("0")


def ensure_user(username: str, group_name: str) -> AbstractUser:
    user, created = UserModel.objects.get_or_create(
        username=username, defaults={"password": "unused"}
    )
    if created:
        user.set_password("ProofPass123!")
        user.save()
    group = Group.objects.get(name=group_name)
    user.groups.add(group)
    return user


def main() -> int:
    print("=== StockDesk Day 7 concurrency proof ===")
    call_command("bootstrap_roles")

    owner = ensure_user("proof_owner", OWNER)
    cashier_a = ensure_user("proof_cashier_a", CASHIER)
    cashier_b = ensure_user("proof_cashier_b", CASHIER)

    cat, _ = Category.objects.get_or_create(name="Concurrency Proof")
    supplier, _ = Supplier.objects.get_or_create(
        name="Proof Supplier", defaults={"phone": "9000000099"}
    )
    product, _ = Product.objects.get_or_create(
        sku="PROOF-LAST-UNIT",
        defaults={
            "name": "Last Unit Widget",
            "category": cat,
            "purchase_price": Decimal("10.00"),
            "sale_price": Decimal("20.00"),
            "sellable": True,
            "is_active": True,
        },
    )

    # Reset stock for this product to exactly 1 via a purchase top-up.
    current = stock_of(product)
    if current != 1:
        delta_needed = Decimal("1") - current
        if delta_needed > 0:
            create_purchase_with_stock(
                supplier=supplier,
                purchase_date=timezone.localdate(),
                supplier_invoice_no="PROOF-IN",
                lines=[{"product": product, "qty": delta_needed, "rate": product.purchase_price}],
                user=owner,
            )
        elif delta_needed < 0:
            # Sell down excess so we start at 1 (sequential, not concurrent).
            create_sale_with_stock(
                customer=None,
                sale_date=timezone.now(),
                lines=[
                    {
                        "product": product,
                        "qty": abs(delta_needed),
                        "rate": product.sale_price,
                    }
                ],
                user=owner,
            )

    start_stock = stock_of(product)
    print(f"Starting stock for {product.sku}: {start_stock}")
    if start_stock != 1:
        print("ERROR: could not prepare stock of exactly 1.")
        return 1

    before_sales = Sale.objects.filter(items__product=product).distinct().count()
    outcomes: list[str] = []
    errors: list[str] = []

    def attempt(username: str) -> None:
        connection.close()
        user = UserModel.objects.get(username=username)
        try:
            sale = create_sale_with_stock(
                customer=None,
                sale_date=timezone.now(),
                lines=[{"product": product, "qty": Decimal("1"), "rate": Decimal("20.00")}],
                user=user,
            )
            outcomes.append(f"SUCCESS:{username}:{sale.invoice_no}")
            print(f"  [{username}] SUCCESS -> {sale.invoice_no}")
        except InsufficientStockError as exc:
            outcomes.append(f"FAIL:{username}")
            print(f"  [{username}] CLEAN FAIL -> {exc}")
        except Exception as exc:  # noqa: BLE001
            outcomes.append(f"ERROR:{username}")
            errors.append(f"{username}: {exc}\n{traceback.format_exc()}")
            print(f"  [{username}] UNEXPECTED ERROR -> {exc}")
        finally:
            connection.close()

    print("Firing two concurrent sales for qty=1 ...")
    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(attempt, cashier_a.username)
        f2 = pool.submit(attempt, cashier_b.username)
        f1.result()
        f2.result()

    end_stock = stock_of(product)
    after_sales = Sale.objects.filter(items__product=product).distinct().count()
    successes = [o for o in outcomes if o.startswith("SUCCESS")]
    fails = [o for o in outcomes if o.startswith("FAIL")]

    print("--- Results ---")
    print(f"Outcomes: {outcomes}")
    print(f"Final stock: {end_stock}")
    print(f"New sales for product: {after_sales - before_sales}")

    ok = (
        len(successes) == 1
        and len(fails) == 1
        and end_stock == Decimal("0")
        and not errors
        and (after_sales - before_sales) == 1
    )
    if ok:
        print("PROOF PASSED: one success, one clean failure, stock never went negative.")
        return 0

    print("PROOF FAILED.")
    for err in errors:
        print(err)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
