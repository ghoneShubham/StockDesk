from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from PIL import Image

from apps.core.permissions import CASHIER, OWNER, STORE_MANAGER
from apps.masters.models import Category, Customer, Product

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
def category(db):
    return Category.objects.create(name="Grocery")


@pytest.fixture
def product(category):
    return Product.objects.create(
        sku="SKU-001",
        name="Rice 1kg",
        category=category,
        purchase_price=Decimal("40.00"),
        sale_price=Decimal("55.00"),
        reorder_level=5,
    )


def _png_upload(name="item.png"):
    buf = BytesIO()
    Image.new("RGB", (32, 32), color=(20, 160, 140)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@pytest.mark.django_db
def test_cashier_can_view_product_list_without_purchase_price(client, user_factory, product):
    user_factory("cashier_p", CASHIER)
    assert client.login(username="cashier_p", password="pass1234!")
    response = client.get(reverse("masters:product_list"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Rice 1kg" in body
    assert "55.00" in body
    assert "Purchase" not in body
    assert "40.00" not in body
    assert ">Filter<" in body
    assert 'name="status"' in body


@pytest.mark.django_db
def test_product_list_status_filter(client, user_factory, product):
    user_factory("cashier_status", CASHIER)
    product.is_active = False
    product.save(update_fields=["is_active"])
    assert client.login(username="cashier_status", password="pass1234!")

    active = client.get(reverse("masters:product_list"), {"status": "active"})
    assert active.status_code == 200
    assert product.name not in active.content.decode()
    assert ">Filter<" in active.content.decode()

    inactive = client.get(reverse("masters:product_list"), {"status": "inactive"})
    assert inactive.status_code == 200
    assert product.name in inactive.content.decode()


@pytest.mark.django_db
def test_cashier_cannot_open_product_create(client, user_factory):
    user_factory("cashier_add", CASHIER)
    assert client.login(username="cashier_add", password="pass1234!")
    response = client.get(reverse("masters:product_create"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_can_create_product_but_not_change_sale_price_on_edit(client, user_factory, category, product):
    user_factory("manager_p", STORE_MANAGER)
    assert client.login(username="manager_p", password="pass1234!")

    create_resp = client.post(
        reverse("masters:product_create"),
        {
            "sku": "SKU-NEW",
            "name": "Sugar 1kg",
            "category": category.pk,
            "unit": "pc",
            "hsn_code": "",
            "purchase_price": "30.00",
            "sale_price": "45.00",
            "reorder_level": "3",
            "sellable": "on",
            "is_active": "on",
        },
    )
    assert create_resp.status_code == 302
    created = Product.objects.get(sku="SKU-NEW")
    assert created.sale_price == Decimal("45.00")

    # Manager edits sale_price — must be ignored (field disabled).
    edit_resp = client.post(
        reverse("masters:product_update", kwargs={"pk": product.pk}),
        {
            "sku": product.sku,
            "name": product.name,
            "category": category.pk,
            "unit": product.unit,
            "hsn_code": "",
            "purchase_price": "41.00",
            "sale_price": "999.00",
            "reorder_level": product.reorder_level,
            "sellable": "on",
            "is_active": "on",
        },
    )
    assert edit_resp.status_code == 302
    product.refresh_from_db()
    assert product.sale_price == Decimal("55.00")
    assert product.purchase_price == Decimal("41.00")


@pytest.mark.django_db
def test_owner_can_change_sale_price(client, user_factory, category, product):
    user_factory("owner_p", OWNER)
    assert client.login(username="owner_p", password="pass1234!")
    response = client.post(
        reverse("masters:product_update", kwargs={"pk": product.pk}),
        {
            "sku": product.sku,
            "name": product.name,
            "category": category.pk,
            "unit": product.unit,
            "hsn_code": "",
            "purchase_price": "40.00",
            "sale_price": "60.00",
            "reorder_level": product.reorder_level,
            "sellable": "on",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    product.refresh_from_db()
    assert product.sale_price == Decimal("60.00")


@pytest.mark.django_db
def test_product_image_upload_accepted(client, user_factory, category):
    user_factory("owner_img", OWNER)
    assert client.login(username="owner_img", password="pass1234!")
    response = client.post(
        reverse("masters:product_create"),
        {
            "sku": "SKU-IMG",
            "name": "Oil 1L",
            "category": category.pk,
            "unit": "l",
            "hsn_code": "",
            "purchase_price": "100.00",
            "sale_price": "130.00",
            "reorder_level": "2",
            "sellable": "on",
            "is_active": "on",
            "image": _png_upload(),
        },
    )
    assert response.status_code == 302
    product = Product.objects.get(sku="SKU-IMG")
    assert product.image.name
    assert product.image.name.endswith(".png")


@pytest.mark.django_db
def test_reject_non_image_upload(client, user_factory, category):
    user_factory("owner_bad", OWNER)
    assert client.login(username="owner_bad", password="pass1234!")
    bad = SimpleUploadedFile("shell.php", b"<?php echo 1; ?>", content_type="application/x-php")
    response = client.post(
        reverse("masters:product_create"),
        {
            "sku": "SKU-BAD",
            "name": "Bad file",
            "category": category.pk,
            "unit": "pc",
            "hsn_code": "",
            "purchase_price": "10.00",
            "sale_price": "12.00",
            "reorder_level": "1",
            "sellable": "on",
            "is_active": "on",
            "image": bad,
        },
    )
    assert response.status_code == 200
    assert not Product.objects.filter(sku="SKU-BAD").exists()
    body = response.content.decode().lower()
    assert "valid image" in body or "not an image" in body or "extension" in body


@pytest.mark.django_db
def test_category_create_shows_success_message(client, user_factory):
    user_factory("manager_c", STORE_MANAGER)
    assert client.login(username="manager_c", password="pass1234!")
    response = client.post(reverse("masters:category_create"), {"name": "Snacks", "is_active": "on"}, follow=True)
    assert response.status_code == 200
    assert Category.objects.filter(name="Snacks").exists()
    messages = list(response.context["messages"])
    assert any("created" in str(m).lower() for m in messages)


@pytest.mark.django_db
def test_customer_unique_phone_validation(client, user_factory):
    user_factory("manager_cu", STORE_MANAGER)
    Customer.objects.create(name="Asha", phone="9876543210")
    assert client.login(username="manager_cu", password="pass1234!")
    response = client.post(
        reverse("masters:customer_create"),
        {"name": "Other", "phone": "9876543210", "address": ""},
    )
    assert response.status_code == 200
    assert Customer.objects.filter(phone="9876543210").count() == 1


@pytest.mark.django_db
def test_product_deactivate_is_soft_delete(client, user_factory, product):
    user_factory("manager_d", STORE_MANAGER)
    assert client.login(username="manager_d", password="pass1234!")
    response = client.post(reverse("masters:product_deactivate", kwargs={"pk": product.pk}))
    assert response.status_code == 302
    product.refresh_from_db()
    assert product.is_active is False
    assert product.sellable is False
    assert Product.objects.filter(pk=product.pk).exists()


@pytest.mark.django_db
def test_next_sku_is_sequential(db):
    from apps.masters.services import next_sku
    from apps.masters.models import SkuSequence

    a = next_sku()
    b = next_sku()
    assert a == "SKU-000001"
    assert b == "SKU-000002"
    assert SkuSequence.objects.get(slug="default").last_number == 2


@pytest.mark.django_db
def test_product_create_auto_generates_sku(client, user_factory, category):
    user_factory("manager_sku", STORE_MANAGER)
    assert client.login(username="manager_sku", password="pass1234!")

    get_resp = client.get(reverse("masters:product_create"))
    assert get_resp.status_code == 200
    body = get_resp.content.decode()
    assert "SKU-000001" in body
    assert "Leave blank to auto-generate" in body

    create_resp = client.post(
        reverse("masters:product_create"),
        {
            "sku": "",
            "name": "Auto SKU Item",
            "category": category.pk,
            "unit": "pc",
            "hsn_code": "",
            "purchase_price": "20.00",
            "sale_price": "30.00",
            "reorder_level": "1",
            "sellable": "on",
            "is_active": "on",
        },
    )
    assert create_resp.status_code == 302
    created = Product.objects.get(name="Auto SKU Item")
    assert created.sku == "SKU-000001"
