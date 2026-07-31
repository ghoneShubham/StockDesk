import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse

from apps.core.permissions import CASHIER, OWNER, STORE_MANAGER

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


@pytest.mark.django_db
def test_bootstrap_roles_creates_three_groups(roles):
    assert set(Group.objects.values_list("name", flat=True)) == {OWNER, STORE_MANAGER, CASHIER}


@pytest.mark.django_db
def test_owner_can_change_sale_price(user_factory):
    owner = user_factory("owner1", OWNER)
    assert owner.has_perm("masters.change_sale_price")


@pytest.mark.django_db
def test_store_manager_cannot_change_sale_price(user_factory):
    manager = user_factory("manager1", STORE_MANAGER)
    assert not manager.has_perm("masters.change_sale_price")


@pytest.mark.django_db
def test_cashier_cannot_view_purchase_price(user_factory):
    cashier = user_factory("cashier1", CASHIER)
    assert not cashier.has_perm("masters.view_purchase_price")


@pytest.mark.django_db
def test_cashier_cannot_add_purchase(user_factory):
    cashier = user_factory("cashier1", CASHIER)
    assert not cashier.has_perm("purchases.add_purchase")


@pytest.mark.django_db
def test_all_roles_can_bill_a_sale(user_factory):
    for username, group in [("owner2", OWNER), ("manager2", STORE_MANAGER), ("cashier2", CASHIER)]:
        user = user_factory(username, group)
        assert user.has_perm("sales.add_sale")


@pytest.mark.django_db
def test_only_owner_can_view_financial_reports(user_factory):
    owner = user_factory("owner3", OWNER)
    manager = user_factory("manager3", STORE_MANAGER)
    cashier = user_factory("cashier3", CASHIER)
    assert owner.has_perm("reports.view_financial_reports")
    assert not manager.has_perm("reports.view_financial_reports")
    assert not cashier.has_perm("reports.view_financial_reports")


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_login_then_dashboard_succeeds(client, user_factory):
    user_factory("someuser", CASHIER)
    logged_in = client.login(username="someuser", password="pass1234!")
    assert logged_in
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 200
