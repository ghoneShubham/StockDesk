from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.permissions import CASHIER, OWNER, STORE_MANAGER
from apps.inventory.models import Adjustment, StockMovement
from apps.inventory.services import AdjustmentError, apply_adjustment, current_stock
from apps.masters.models import Category, Product, Supplier
from apps.purchases.services import create_purchase_with_stock
from apps.sales.services import create_sale_with_stock

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
    cat = Category.objects.create(name="Adj Cat")
    supplier = Supplier.objects.create(name="Adj Supplier", phone="9333333333")
    product = Product.objects.create(
        sku="ADJ-100",
        name="Adjustable Widget",
        category=cat,
        purchase_price=Decimal("10.00"),
        sale_price=Decimal("15.00"),
        reorder_level=2,
    )
    return {"category": cat, "supplier": supplier, "product": product}


def stock_of(product):
    total = StockMovement.objects.filter(product=product).aggregate(s=Sum("qty_delta"))["s"]
    return total or Decimal("0")


@pytest.mark.django_db
def test_apply_adjustment_writes_movement_atomically(user_factory, catalog):
    owner = user_factory("owner_adj", OWNER)
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="IN",
        lines=[{"product": catalog["product"], "qty": Decimal("10"), "rate": Decimal("10")}],
        user=owner,
    )
    adj = apply_adjustment(
        product=catalog["product"],
        qty_delta=Decimal("-3"),
        reason=Adjustment.Reason.DAMAGE,
        notes="Broken in transit",
        user=owner,
    )
    assert adj.stock_movement_id is not None
    assert adj.stock_movement.qty_delta == Decimal("-3.00")
    assert adj.stock_movement.reference_type == StockMovement.ReferenceType.ADJUSTMENT
    assert stock_of(catalog["product"]) == Decimal("7")
    assert current_stock(catalog["product"].pk) == Decimal("7")


@pytest.mark.django_db
def test_adjustment_cannot_drive_stock_negative(user_factory, catalog):
    owner = user_factory("owner_adj_neg", OWNER)
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="IN2",
        lines=[{"product": catalog["product"], "qty": Decimal("2"), "rate": Decimal("10")}],
        user=owner,
    )
    with pytest.raises(AdjustmentError):
        apply_adjustment(
            product=catalog["product"],
            qty_delta=Decimal("-5"),
            reason=Adjustment.Reason.THEFT,
            user=owner,
        )
    assert Adjustment.objects.count() == 0
    assert stock_of(catalog["product"]) == Decimal("2")


@pytest.mark.django_db
def test_opening_stock_adjustment(user_factory, catalog):
    owner = user_factory("owner_open", OWNER)
    adj = apply_adjustment(
        product=catalog["product"],
        qty_delta=Decimal("25"),
        reason=Adjustment.Reason.OPENING_STOCK,
        notes="Go-live count",
        user=owner,
    )
    assert adj.stock_movement.movement_type == StockMovement.MovementType.OPENING
    assert stock_of(catalog["product"]) == Decimal("25")


@pytest.mark.django_db
def test_stock_history_matches_mixed_sequence(user_factory, catalog):
    owner = user_factory("owner_hist", OWNER)
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="H1",
        lines=[{"product": catalog["product"], "qty": Decimal("10"), "rate": Decimal("10")}],
        user=owner,
    )
    create_sale_with_stock(
        customer=None,
        sale_date=timezone.now(),
        lines=[{"product": catalog["product"], "qty": Decimal("3"), "rate": Decimal("15")}],
        user=owner,
    )
    apply_adjustment(
        product=catalog["product"],
        qty_delta=Decimal("-1"),
        reason=Adjustment.Reason.DAMAGE,
        user=owner,
    )
    assert stock_of(catalog["product"]) == Decimal("6")
    assert client_stock_history_balance(owner, catalog["product"]) == Decimal("6")


def client_stock_history_balance(user, product):
    """Helper: compute running balance the same way the history view does."""
    running = Decimal("0")
    for m in StockMovement.objects.filter(product=product).order_by("created_at", "id"):
        running += m.qty_delta
    return running


@pytest.mark.django_db
def test_manager_can_create_adjustment_via_form(client, user_factory, catalog):
    owner = user_factory("owner_for_adj_stock", OWNER)
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="M1",
        lines=[{"product": catalog["product"], "qty": Decimal("5"), "rate": Decimal("10")}],
        user=owner,
    )
    user_factory("manager_adj", STORE_MANAGER)
    assert client.login(username="manager_adj", password="pass1234!")
    create_page = client.get(reverse("inventory:adjustment_create"))
    assert create_page.status_code == 200
    create_body = create_page.content.decode()
    assert "type_to_select.js" in create_body
    assert "data-type-select" in create_body
    assert catalog["product"].name in create_body
    response = client.post(
        reverse("inventory:adjustment_create"),
        {
            "product": catalog["product"].pk,
            "qty_delta": "-2",
            "reason": Adjustment.Reason.CORRECTION,
            "notes": "Cycle count",
        },
    )
    assert response.status_code == 302, response.content.decode()[:500]
    assert stock_of(catalog["product"]) == Decimal("3")
    assert Adjustment.objects.count() == 1


@pytest.mark.django_db
def test_cashier_cannot_create_or_list_adjustments(client, user_factory):
    user_factory("cashier_adj", CASHIER)
    assert client.login(username="cashier_adj", password="pass1234!")
    assert client.get(reverse("inventory:adjustment_list")).status_code == 403
    assert client.get(reverse("inventory:adjustment_create")).status_code == 403


@pytest.mark.django_db
def test_stock_history_view_requires_permission(client, user_factory, catalog):
    owner = user_factory("owner_hist_view", OWNER)
    user_factory("cashier_hist", CASHIER)
    assert client.login(username="cashier_hist", password="pass1234!")
    # Cashier has no view_stockmovement
    assert (
        client.get(reverse("inventory:product_stock_history", kwargs={"pk": catalog["product"].pk})).status_code
        == 403
    )
    assert client.login(username="owner_hist_view", password="pass1234!")
    response = client.get(
        reverse("inventory:product_stock_history", kwargs={"pk": catalog["product"].pk})
    )
    assert response.status_code == 200
    assert b"Stock history" in response.content


@pytest.mark.django_db
def test_reconcile_stock_ok_and_detects_drift(user_factory, catalog):
    owner = user_factory("owner_recon", OWNER)
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="R1",
        lines=[{"product": catalog["product"], "qty": Decimal("4"), "rate": Decimal("10")}],
        user=owner,
    )
    apply_adjustment(
        product=catalog["product"],
        qty_delta=Decimal("1"),
        reason=Adjustment.Reason.CORRECTION,
        user=owner,
    )
    out = StringIO()
    call_command("reconcile_stock", stdout=out)
    assert "OK" in out.getvalue()

    # Corrupt a movement to force drift.
    move = StockMovement.objects.filter(
        reference_type=StockMovement.ReferenceType.PURCHASE
    ).first()
    move.qty_delta = Decimal("99")
    move.save(update_fields=["qty_delta"])

    out2 = StringIO()
    with pytest.raises(SystemExit):
        call_command("reconcile_stock", "--fail-on-drift", stdout=out2)
    assert "issue" in out2.getvalue().lower() or "Purchase" in out2.getvalue()
