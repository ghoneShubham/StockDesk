"""Day 11 — report permissions, date filters, CSV, and total sanity checks."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.core.permissions import CASHIER, OWNER, STORE_MANAGER
from apps.masters.models import Category, Customer, Product, Supplier
from apps.purchases.services import create_purchase_with_stock
from apps.reports import queries
from apps.sales.models import Sale
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
    cat = Category.objects.create(name="ReportCat")
    product = Product.objects.create(
        sku="RPT-1",
        name="Report Widget",
        category=cat,
        purchase_price=Decimal("40.00"),
        sale_price=Decimal("100.00"),
        reorder_level=5,
    )
    supplier = Supplier.objects.create(name="Report Supplier")
    customer = Customer.objects.create(name="Report Customer", phone="9999900011")
    return {"product": product, "supplier": supplier, "customer": customer, "category": cat}


@pytest.mark.django_db
def test_cashier_cannot_open_operational_report(client, user_factory):
    user_factory("cashier_ops", CASHIER)
    assert client.login(username="cashier_ops", password="pass1234!")
    assert client.get(reverse("reports:daily_sales")).status_code == 403
    assert client.get(reverse("reports:low_stock")).status_code == 403


@pytest.mark.django_db
def test_manager_can_open_operational_but_not_financial(client, user_factory):
    user_factory("manager_ops", STORE_MANAGER)
    assert client.login(username="manager_ops", password="pass1234!")
    assert client.get(reverse("reports:daily_sales")).status_code == 200
    assert client.get(reverse("reports:stock_valuation")).status_code == 403
    assert client.get(reverse("reports:profit_margin")).status_code == 403


@pytest.mark.django_db
def test_owner_can_open_financial_reports(client, user_factory):
    user_factory("owner_fin2", OWNER)
    assert client.login(username="owner_fin2", password="pass1234!")
    assert client.get(reverse("reports:financial")).status_code == 200
    assert client.get(reverse("reports:stock_valuation")).status_code == 200
    assert client.get(reverse("reports:profit_margin")).status_code == 200


@pytest.mark.django_db
def test_daily_sales_includes_zero_days_and_matches_sum(user_factory, catalog):
    owner = user_factory("owner_daily", OWNER)
    product = catalog["product"]
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="D1",
        lines=[{"product": product, "qty": Decimal("20"), "rate": product.purchase_price}],
        user=owner,
    )
    create_sale_with_stock(
        customer=catalog["customer"],
        sale_date=timezone.now(),
        lines=[{"product": product, "qty": Decimal("2"), "rate": Decimal("100.00"), "discount": Decimal("0")}],
        user=owner,
        header_discount=Decimal("0"),
        tax=Decimal("0"),
    )
    date_from = timezone.localdate() - timedelta(days=2)
    date_to = timezone.localdate()
    rows = queries.daily_sales_totals(date_from, date_to)
    assert len(rows) == 3
    assert sum(r["invoice_count"] for r in rows) == 1
    assert sum(r["total_sales"] for r in rows) == Decimal("200.00")
    assert any(r["invoice_count"] == 0 for r in rows)


@pytest.mark.django_db
def test_profit_margin_handles_zero_revenue_and_math(user_factory, catalog):
    owner = user_factory("owner_margin", OWNER)
    product = catalog["product"]
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="M1",
        lines=[{"product": product, "qty": Decimal("10"), "rate": product.purchase_price}],
        user=owner,
    )
    create_sale_with_stock(
        customer=None,
        sale_date=timezone.now(),
        lines=[{"product": product, "qty": Decimal("1"), "rate": Decimal("100.00"), "discount": Decimal("0")}],
        user=owner,
    )
    rows = queries.profit_margin_by_product(timezone.localdate(), timezone.localdate())
    assert len(rows) == 1
    row = rows[0]
    assert row["revenue"] == Decimal("100.00")
    assert row["cost"] == Decimal("40.00")
    assert row["profit"] == Decimal("60.00")
    assert row["margin_pct"] == Decimal("60.00")


@pytest.mark.django_db
def test_integrity_report_flags_mismatched_header(user_factory, catalog):
    owner = user_factory("owner_int", OWNER)
    product = catalog["product"]
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="I1",
        lines=[{"product": product, "qty": Decimal("5"), "rate": product.purchase_price}],
        user=owner,
    )
    sale = create_sale_with_stock(
        customer=None,
        sale_date=timezone.now(),
        lines=[{"product": product, "qty": Decimal("1"), "rate": Decimal("50.00"), "discount": Decimal("0")}],
        user=owner,
    )
    Sale.objects.filter(pk=sale.pk).update(total_amount=Decimal("999.99"))
    issues = queries.invoice_integrity_issues()
    assert any(i["invoice_no"] == sale.invoice_no for i in issues)


@pytest.mark.django_db
def test_daily_sales_csv_export(client, user_factory):
    user_factory("owner_csv", OWNER)
    assert client.login(username="owner_csv", password="pass1234!")
    response = client.get(reverse("reports:daily_sales"), {"export": "csv"})
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert b"Date" in response.content


@pytest.mark.django_db
def test_dashboard_shows_metrics(client, user_factory, catalog):
    owner = user_factory("owner_dash", OWNER)
    create_purchase_with_stock(
        supplier=catalog["supplier"],
        purchase_date=timezone.localdate(),
        supplier_invoice_no="DASH",
        lines=[{"product": catalog["product"], "qty": Decimal("3"), "rate": catalog["product"].purchase_price}],
        user=owner,
    )
    create_sale_with_stock(
        customer=catalog["customer"],
        sale_date=timezone.now(),
        lines=[{"product": catalog["product"], "qty": Decimal("1"), "rate": Decimal("100.00"), "discount": Decimal("0")}],
        user=owner,
    )
    assert client.login(username="owner_dash", password="pass1234!")
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 200
    assert response.context["today_total"] == Decimal("100.00")
    assert response.context["today_count"] == 1
