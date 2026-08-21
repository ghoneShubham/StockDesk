from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.permissions import CASHIER, OWNER, STORE_MANAGER

# Every (app_label, codename) tuple a group needs. Kept as plain data (not
# hardcoded per-view checks) so the whole permission matrix in PRD Section 3
# can be read, reviewed, and diffed in one place.

OWNER_PERMS = [
    # Owner gets every permission on every StockDesk model — full control,
    # including user management via /admin/. Real owner accounts should also
    # be created with is_staff=True (and ideally is_superuser=True) so they
    # can reach Django admin for one-off fixes (PRD Module A).
    ("masters", "add_category"), ("masters", "change_category"),
    ("masters", "delete_category"), ("masters", "view_category"),
    ("masters", "add_product"), ("masters", "change_product"),
    ("masters", "delete_product"), ("masters", "view_product"),
    ("masters", "view_purchase_price"), ("masters", "change_sale_price"),
    ("masters", "add_supplier"), ("masters", "change_supplier"),
    ("masters", "delete_supplier"), ("masters", "view_supplier"),
    ("masters", "add_customer"), ("masters", "change_customer"),
    ("masters", "delete_customer"), ("masters", "view_customer"),
    ("purchases", "add_purchase"), ("purchases", "change_purchase"),
    ("purchases", "delete_purchase"), ("purchases", "view_purchase"),
    ("purchases", "add_purchaseitem"), ("purchases", "change_purchaseitem"),
    ("purchases", "delete_purchaseitem"), ("purchases", "view_purchaseitem"),
    ("sales", "add_sale"), ("sales", "change_sale"),
    ("sales", "delete_sale"), ("sales", "view_sale"),
    ("sales", "add_saleitem"), ("sales", "change_saleitem"),
    ("sales", "delete_saleitem"), ("sales", "view_saleitem"),
    ("inventory", "add_adjustment"), ("inventory", "view_adjustment"),
    ("inventory", "view_stockmovement"),
    ("reports", "view_financial_reports"), ("reports", "view_operational_reports"),
    ("payments", "add_paymentlink"), ("payments", "view_paymentlink"),
    ("payments", "view_paymentevent"),
    ("auth", "add_user"), ("auth", "change_user"), ("auth", "delete_user"), ("auth", "view_user"),
    ("auth", "add_group"), ("auth", "change_group"), ("auth", "view_group"),
]

STORE_MANAGER_PERMS = [
    # View + edit masters, but NOT change_sale_price (owner-only, PRD Section 3).
    ("masters", "view_category"), ("masters", "add_category"), ("masters", "change_category"),
    ("masters", "view_product"), ("masters", "add_product"), ("masters", "change_product"),
    ("masters", "view_purchase_price"),
    ("masters", "view_supplier"), ("masters", "add_supplier"), ("masters", "change_supplier"),
    ("masters", "view_customer"), ("masters", "add_customer"), ("masters", "change_customer"),
    ("purchases", "add_purchase"), ("purchases", "change_purchase"), ("purchases", "view_purchase"),
    ("purchases", "add_purchaseitem"), ("purchases", "change_purchaseitem"), ("purchases", "view_purchaseitem"),
    ("sales", "add_sale"), ("sales", "view_sale"),
    ("sales", "add_saleitem"), ("sales", "view_saleitem"),
    ("inventory", "add_adjustment"), ("inventory", "view_adjustment"),
    ("inventory", "view_stockmovement"),
    ("reports", "view_operational_reports"),
    ("payments", "add_paymentlink"), ("payments", "view_paymentlink"),
]

CASHIER_PERMS = [
    # View-only masters, and note: purchase_price is deliberately NOT granted.
    ("masters", "view_category"),
    ("masters", "view_product"),
    ("masters", "view_supplier"),
    ("masters", "view_customer"),
    ("sales", "add_sale"), ("sales", "view_sale"),
    ("sales", "add_saleitem"), ("sales", "view_saleitem"),
    ("payments", "add_paymentlink"), ("payments", "view_paymentlink"),
]

ROLE_PERMS = {
    OWNER: OWNER_PERMS,
    STORE_MANAGER: STORE_MANAGER_PERMS,
    CASHIER: CASHIER_PERMS,
}


class Command(BaseCommand):
    help = "Create/update the Owner, Store Manager, and Cashier groups with the permission matrix from PRD Section 3."

    @transaction.atomic
    def handle(self, *args, **options):
        for role_name, perm_specs in ROLE_PERMS.items():
            group, created = Group.objects.get_or_create(name=role_name)
            permissions = []
            missing = []
            for app_label, codename in perm_specs:
                try:
                    permissions.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
                except Permission.DoesNotExist:
                    missing.append(f"{app_label}.{codename}")

            group.permissions.set(permissions)

            verb = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{verb} group '{role_name}' with {len(permissions)} permissions."))
            if missing:
                self.stdout.write(
                    self.style.WARNING(f"  Skipped {len(missing)} not-yet-existing permissions: {', '.join(missing)}")
                )
