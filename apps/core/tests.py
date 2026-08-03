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
def test_cashier_gets_403_on_financial_reports(client, user_factory):
    """PRD Section 3 / test #7 — Cashier cannot open a margin/financial report."""
    user_factory("cashier_fin", CASHIER)
    assert client.login(username="cashier_fin", password="pass1234!")
    response = client.get(reverse("reports:financial"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_gets_403_on_financial_reports(client, user_factory):
    user_factory("manager_fin", STORE_MANAGER)
    assert client.login(username="manager_fin", password="pass1234!")
    response = client.get(reverse("reports:financial"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_can_open_financial_reports(client, user_factory):
    user_factory("owner_fin", OWNER)
    assert client.login(username="owner_fin", password="pass1234!")
    response = client.get(reverse("reports:financial"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_cashier_gets_403_on_purchases(client, user_factory):
    user_factory("cashier_pur", CASHIER)
    assert client.login(username="cashier_pur", password="pass1234!")
    response = client.get(reverse("purchases:purchase_list"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_can_open_purchases(client, user_factory):
    user_factory("manager_pur", STORE_MANAGER)
    assert client.login(username="manager_pur", password="pass1234!")
    response = client.get(reverse("purchases:purchase_list"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_cashier_can_open_sales_list(client, user_factory):
    user_factory("cashier_sale", CASHIER)
    assert client.login(username="cashier_sale", password="pass1234!")
    response = client.get(reverse("sales:sale_list"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_anonymous_redirected_from_protected_purchase_view(client):
    response = client.get(reverse("purchases:purchase_list"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_logout_requires_post_and_clears_session(client, user_factory):
    user_factory("logout_user", CASHIER)
    assert client.login(username="logout_user", password="pass1234!")
    assert client.get(reverse("core:dashboard")).status_code == 200

    # Django 5 LogoutView only accepts POST.
    response = client.post(reverse("accounts:logout"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url
    assert client.get(reverse("core:dashboard")).status_code == 302
