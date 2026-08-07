from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.permissions import CASHIER, OWNER, STORE_MANAGER
from apps.inventory.models import StockMovement
from apps.masters.models import Category, Product, Supplier
from apps.purchases.models import Purchase, PurchaseItem
from apps.purchases.services import create_purchase_with_stock

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
    cat = Category.objects.create(name="Test Cat")
    supplier = Supplier.objects.create(name="Acme Supplies", phone="9000000001")
    p1 = Product.objects.create(
        sku="P-100",
        name="Widget",
        category=cat,
        purchase_price=Decimal("10.00"),
        sale_price=Decimal("15.00"),
    )
    p2 = Product.objects.create(
        sku="P-200",
        name="Gadget",
        category=cat,
        purchase_price=Decimal("20.00"),
        sale_price=Decimal("30.00"),
    )
    return {"category": cat, "supplier": supplier, "p1": p1, "p2": p2}


def stock_of(product):
    total = StockMovement.objects.filter(product=product).aggregate(s=Sum("qty_delta"))["s"]
    return total or Decimal("0")


@pytest.mark.django_db
def test_create_purchase_increases_stock_atomically(user_factory, catalog):
    owner = user_factory("owner_pur", OWNER)
    purchase = create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="SIN-1",
        lines=[
            {"product": catalog["p1"], "qty": Decimal("5"), "rate": Decimal("10.00")},
            {"product": catalog["p2"], "qty": Decimal("3"), "rate": Decimal("20.00")},
        ],
        user=owner,
    )
    assert purchase.total_amount == Decimal("110.00")
    assert purchase.items.count() == 2
    assert stock_of(catalog["p1"]) == Decimal("5")
    assert stock_of(catalog["p2"]) == Decimal("3")
    assert (
        StockMovement.objects.filter(
            reference_type=StockMovement.ReferenceType.PURCHASE, reference_id=purchase.pk
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_failed_purchase_leaves_no_partial_data(user_factory, catalog):
    owner = user_factory("owner_fail", OWNER)
    before_purchases = Purchase.objects.count()
    before_items = PurchaseItem.objects.count()
    before_moves = StockMovement.objects.count()

    with pytest.raises(ValueError):
        create_purchase_with_stock(
            supplier=catalog["supplier"],
            purchase_date=timezone.localdate(),
            supplier_invoice_no="SIN-BAD",
            lines=[
                {"product": catalog["p1"], "qty": Decimal("2"), "rate": Decimal("10.00")},
                {"product": catalog["p2"], "qty": Decimal("0"), "rate": Decimal("20.00")},
            ],
            user=owner,
        )

    assert Purchase.objects.count() == before_purchases
    assert PurchaseItem.objects.count() == before_items
    assert StockMovement.objects.count() == before_moves


@pytest.mark.django_db
def test_manager_can_create_purchase_via_form(client, user_factory, catalog):
    user_factory("manager_pur", STORE_MANAGER)
    assert client.login(username="manager_pur", password="pass1234!")
    response = client.get(reverse("purchases:purchase_create"))
    assert response.status_code == 200

    payload = {
        "supplier": catalog["supplier"].pk,
        "supplier_invoice_no": "INV-99",
        "purchase_date": timezone.localdate().isoformat(),
        "items-TOTAL_FORMS": "1",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "items-0-product": catalog["p1"].pk,
        "items-0-qty": "4",
        "items-0-rate": "10.00",
    }
    response = client.post(reverse("purchases:purchase_create"), payload)
    assert response.status_code == 302, response.content.decode()[:500]
    purchase = Purchase.objects.latest("id")
    assert purchase.total_amount == Decimal("40.00")
    assert stock_of(catalog["p1"]) == Decimal("4")


@pytest.mark.django_db
def test_cashier_cannot_create_purchase(client, user_factory):
    user_factory("cashier_pur2", CASHIER)
    assert client.login(username="cashier_pur2", password="pass1234!")
    assert client.get(reverse("purchases:purchase_create")).status_code == 403


@pytest.mark.django_db
def test_purchase_list_shows_created_rows(client, user_factory, catalog):
    owner = user_factory("owner_list", OWNER)
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="LIST-1",
        lines=[{"product": catalog["p1"], "qty": Decimal("1"), "rate": Decimal("10.00")}],
        user=owner,
    )
    assert client.login(username="owner_list", password="pass1234!")
    response = client.get(reverse("purchases:purchase_list"))
    assert response.status_code == 200
    assert b"Acme Supplies" in response.content
