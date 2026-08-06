from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.permissions import CASHIER, OWNER, STORE_MANAGER
from apps.inventory.models import StockMovement
from apps.masters.models import Category, Customer, Product
from apps.purchases.services import create_purchase_with_stock
from apps.masters.models import Supplier
from apps.sales.models import InvoiceSequence, Sale, SaleItem
from apps.sales.services import (
    InsufficientStockError,
    create_sale_with_stock,
    current_stock,
    financial_year_for,
    next_invoice_no,
)

User = get_user_model()


@pytest.fixture
def roles(db):
    call_command("bootstrap_roles")


@pytest.fixture
def user_factory(db, roles):
    def make(username, group_name, **extra):
        user = User.objects.create_user(username=username, password="pass1234!", **extra)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    return make


@pytest.fixture
def catalog(db):
    cat = Category.objects.create(name="Sale Cat")
    supplier = Supplier.objects.create(name="Stock In Co", phone="9111111111")
    customer = Customer.objects.create(name="Ravi Buyer", phone="9222222222")
    p1 = Product.objects.create(
        sku="S-100",
        name="Bolt",
        category=cat,
        purchase_price=Decimal("10.00"),
        sale_price=Decimal("15.00"),
    )
    p2 = Product.objects.create(
        sku="S-200",
        name="Nut",
        category=cat,
        purchase_price=Decimal("5.00"),
        sale_price=Decimal("9.00"),
    )
    return {"category": cat, "supplier": supplier, "customer": customer, "p1": p1, "p2": p2}


def stock_of(product):
    total = StockMovement.objects.filter(product=product).aggregate(s=Sum("qty_delta"))["s"]
    return total or Decimal("0")


def stock_in(user, catalog, product, qty):
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="STOCK",
        lines=[{"product": product, "qty": qty, "rate": product.purchase_price}],
        user=user,
    )


@pytest.mark.django_db
def test_create_sale_decreases_stock_and_totals(user_factory, catalog):
    owner = user_factory("owner_sale", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("10"))
    stock_in(owner, catalog, catalog["p2"], Decimal("5"))

    sale = create_sale_with_stock(
        customer=catalog["customer"],
        sale_date=timezone.now(),
        lines=[
            {
                "product": catalog["p1"],
                "qty": Decimal("2"),
                "rate": Decimal("15.00"),
                "discount": Decimal("1.00"),
            },
            {
                "product": catalog["p2"],
                "qty": Decimal("1"),
                "rate": Decimal("9.00"),
                "discount": Decimal("0"),
            },
        ],
        header_discount=Decimal("2.00"),
        tax=Decimal("1.50"),
        payment_status=Sale.PaymentStatus.PAID,
        user=owner,
    )

    # line amounts: (30-1)=29 + 9 = 38; total = 38 - 2 + 1.50 = 37.50
    assert sale.subtotal == Decimal("38.00")
    assert sale.discount == Decimal("2.00")
    assert sale.tax == Decimal("1.50")
    assert sale.total_amount == Decimal("37.50")
    assert sale.items.count() == 2
    assert stock_of(catalog["p1"]) == Decimal("8")
    assert stock_of(catalog["p2"]) == Decimal("4")
    assert sale.invoice_no.startswith("INV-")
    assert (
        StockMovement.objects.filter(
            reference_type=StockMovement.ReferenceType.SALE, reference_id=sale.pk
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_stock_cannot_go_negative(user_factory, catalog):
    owner = user_factory("owner_neg", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("1"))

    with pytest.raises(InsufficientStockError):
        create_sale_with_stock(
            customer=None,
            sale_date=timezone.now(),
            lines=[{"product": catalog["p1"], "qty": Decimal("2"), "rate": Decimal("15.00")}],
            user=owner,
        )

    assert stock_of(catalog["p1"]) == Decimal("1")
    assert Sale.objects.count() == 0
    assert SaleItem.objects.count() == 0


@pytest.mark.django_db
def test_failed_sale_leaves_no_partial_data(user_factory, catalog):
    owner = user_factory("owner_fail_sale", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("5"))
    before_moves = StockMovement.objects.count()

    with pytest.raises(Exception):
        create_sale_with_stock(
            customer=None,
            sale_date=timezone.now(),
            lines=[
                {"product": catalog["p1"], "qty": Decimal("1"), "rate": Decimal("15.00")},
                {"product": catalog["p2"], "qty": Decimal("0"), "rate": Decimal("9.00")},
            ],
            user=owner,
        )

    assert Sale.objects.count() == 0
    assert SaleItem.objects.count() == 0
    assert StockMovement.objects.count() == before_moves
    assert stock_of(catalog["p1"]) == Decimal("5")


@pytest.mark.django_db
def test_line_items_sum_to_header_subtotal(user_factory, catalog):
    owner = user_factory("owner_sum", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("10"))
    sale = create_sale_with_stock(
        customer=None,
        sale_date=timezone.now(),
        lines=[
            {
                "product": catalog["p1"],
                "qty": Decimal("3"),
                "rate": Decimal("15.00"),
                "discount": Decimal("2.50"),
            }
        ],
        header_discount=Decimal("1.00"),
        tax=Decimal("0.50"),
        user=owner,
    )
    lines_sum = sum((i.amount for i in sale.items.all()), Decimal("0"))
    assert lines_sum == sale.subtotal
    assert sale.total_amount == money_like(sale.subtotal - sale.discount + sale.tax)


def money_like(v):
    return Decimal(str(v)).quantize(Decimal("0.01"))


@pytest.mark.django_db
def test_discount_cannot_exceed_line_amount(user_factory, catalog):
    owner = user_factory("owner_disc", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("5"))
    with pytest.raises(Exception):
        create_sale_with_stock(
            customer=None,
            sale_date=timezone.now(),
            lines=[
                {
                    "product": catalog["p1"],
                    "qty": Decimal("1"),
                    "rate": Decimal("15.00"),
                    "discount": Decimal("20.00"),
                }
            ],
            user=owner,
        )
    assert Sale.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_sales_last_unit_one_wins(user_factory, catalog):
    owner = user_factory("owner_conc", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("1"))
    product_id = catalog["p1"].pk

    outcomes = []

    def attempt(username):
        connection.close()
        user = User.objects.get(username=username)
        try:
            create_sale_with_stock(
                customer=None,
                sale_date=timezone.now(),
                lines=[{"product_id": product_id, "qty": Decimal("1"), "rate": Decimal("15.00")}],
                user=user,
            )
            outcomes.append("ok")
        except InsufficientStockError:
            outcomes.append("fail")
        finally:
            connection.close()

    cashier_a = user_factory("cashier_a", CASHIER)
    cashier_b = user_factory("cashier_b", CASHIER)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(attempt, cashier_a.username)
        f2 = pool.submit(attempt, cashier_b.username)
        f1.result()
        f2.result()

    assert outcomes.count("ok") == 1
    assert outcomes.count("fail") == 1
    assert stock_of(catalog["p1"]) == Decimal("0")
    assert Sale.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_invoice_numbers_unique_under_concurrency(user_factory, catalog):
    owner = user_factory("owner_inv", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("20"))
    product_id = catalog["p1"].pk
    invoice_nos = []

    def attempt(i):
        connection.close()
        user = User.objects.get(username="owner_inv")
        sale = create_sale_with_stock(
            customer=None,
            sale_date=timezone.now(),
            lines=[{"product_id": product_id, "qty": Decimal("1"), "rate": Decimal("15.00")}],
            user=user,
        )
        invoice_nos.append(sale.invoice_no)
        connection.close()

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(attempt, range(5)))

    assert len(invoice_nos) == 5
    assert len(set(invoice_nos)) == 5


@pytest.mark.django_db
def test_cashier_can_create_sale_via_form(client, user_factory, catalog):
    owner = user_factory("owner_for_stock", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("5"))
    user_factory("cashier_sale", CASHIER)
    assert client.login(username="cashier_sale", password="pass1234!")
    assert client.get(reverse("sales:sale_create")).status_code == 200

    when = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
    payload = {
        "customer": "",
        "sale_date": when,
        "discount": "0",
        "tax": "0",
        "payment_status": Sale.PaymentStatus.PAID,
        "items-TOTAL_FORMS": "5",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "items-0-product": catalog["p1"].pk,
        "items-0-qty": "2",
        "items-0-rate": "15.00",
        "items-0-discount": "0",
        "items-1-product": "",
        "items-1-qty": "",
        "items-1-rate": "",
        "items-1-discount": "",
        "items-2-product": "",
        "items-2-qty": "",
        "items-2-rate": "",
        "items-2-discount": "",
        "items-3-product": "",
        "items-3-qty": "",
        "items-3-rate": "",
        "items-3-discount": "",
        "items-4-product": "",
        "items-4-qty": "",
        "items-4-rate": "",
        "items-4-discount": "",
    }
    response = client.post(reverse("sales:sale_create"), payload)
    assert response.status_code == 302, response.content.decode()[:800]
    sale = Sale.objects.latest("id")
    assert sale.total_amount == Decimal("30.00")
    assert stock_of(catalog["p1"]) == Decimal("3")


@pytest.mark.django_db
def test_manager_can_view_sales_list(client, user_factory, catalog):
    owner = user_factory("owner_list_sale", OWNER)
    stock_in(owner, catalog, catalog["p1"], Decimal("2"))
    create_sale_with_stock(
        customer=catalog["customer"],
        sale_date=timezone.now(),
        lines=[{"product": catalog["p1"], "qty": Decimal("1"), "rate": Decimal("15.00")}],
        user=owner,
    )
    user_factory("manager_sale", STORE_MANAGER)
    assert client.login(username="manager_sale", password="pass1234!")
    response = client.get(reverse("sales:sale_list"))
    assert response.status_code == 200
    assert b"INV-" in response.content


@pytest.mark.django_db
def test_next_invoice_no_is_sequential(db):
    from django.db import transaction

    when = timezone.now()
    fy = financial_year_for(timezone.localtime(when))
    with transaction.atomic():
        a = next_invoice_no(when=when)
        b = next_invoice_no(when=when)
    assert a != b
    assert a.endswith("000001")
    assert b.endswith("000002")
    assert InvoiceSequence.objects.get(financial_year=fy).last_number == 2
