"""Day 10 — query-budget guards for the hottest list pages."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.permissions import OWNER
from apps.masters.models import Category, Product, Supplier
from apps.purchases.services import create_purchase_with_stock
from apps.sales.services import create_sale_with_stock

User = get_user_model()

# Exclude debug-toolbar middleware so query counts reflect the view only.
_LIGHT_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
]


@pytest.fixture
def roles(db):
    call_command("bootstrap_roles")


@pytest.fixture
def owner(db, roles):
    user = User.objects.create_user(username="perf_owner", password="pass1234!")
    user.groups.add(Group.objects.get(name=OWNER))
    return user


@pytest.fixture
def seeded(db, owner):
    cat = Category.objects.create(name="Perf Cat")
    supplier = Supplier.objects.create(name="Perf Supplier", phone="9444444444")
    products = []
    for i in range(5):
        products.append(
            Product.objects.create(
                sku=f"PERF-{i}",
                name=f"Perf Product {i}",
                category=cat,
                purchase_price=Decimal("10.00"),
                sale_price=Decimal("15.00"),
            )
        )
    for p in products:
        create_purchase_with_stock(
            supplier=supplier,
            purchase_date=timezone.localdate(),
            supplier_invoice_no="P",
            lines=[{"product": p, "qty": Decimal("10"), "rate": Decimal("10")}],
            user=owner,
        )
    for _ in range(3):
        create_sale_with_stock(
            customer=None,
            sale_date=timezone.now(),
            lines=[{"product": products[0], "qty": Decimal("1"), "rate": Decimal("15")}],
            user=owner,
        )
    return {"products": products, "supplier": supplier}


@pytest.mark.django_db
@override_settings(DEBUG=True, MIDDLEWARE=_LIGHT_MIDDLEWARE)
def test_sales_list_stays_under_query_budget(client, owner, seeded):
    assert client.login(username="perf_owner", password="pass1234!")
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse("sales:sale_list"))
    assert response.status_code == 200
    assert len(ctx) <= 15, f"Sales list used {len(ctx)} queries:\n" + "\n".join(
        q["sql"] for q in ctx.captured_queries
    )


@pytest.mark.django_db
@override_settings(DEBUG=True, MIDDLEWARE=_LIGHT_MIDDLEWARE)
def test_product_list_stays_under_query_budget(client, owner, seeded):
    assert client.login(username="perf_owner", password="pass1234!")
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse("masters:product_list"))
    assert response.status_code == 200
    assert len(ctx) <= 15, f"Product list used {len(ctx)} queries:\n" + "\n".join(
        q["sql"] for q in ctx.captured_queries
    )
