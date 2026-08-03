from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.core.permissions import CASHIER, OWNER, STORE_MANAGER

User = get_user_model()

# Demo logins for local/staging — change passwords before any real deployment.
ROLE_USERS = (
    {"username": "owner", "password": "OwnerPass123!", "group": OWNER, "is_staff": True, "is_superuser": True},
    {"username": "manager", "password": "ManagerPass123!", "group": STORE_MANAGER, "is_staff": False, "is_superuser": False},
    {"username": "cashier", "password": "CashierPass123!", "group": CASHIER, "is_staff": False, "is_superuser": False},
)


class Command(BaseCommand):
    help = "Create one demo user per role (Owner / Store Manager / Cashier) and assign groups."

    def handle(self, *args, **options):
        call_command("bootstrap_roles")

        for spec in ROLE_USERS:
            user, created = User.objects.get_or_create(username=spec["username"])
            user.set_password(spec["password"])
            user.is_staff = spec["is_staff"]
            user.is_superuser = spec["is_superuser"]
            user.is_active = True
            user.save()

            group = Group.objects.get(name=spec["group"])
            user.groups.set([group])

            verb = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(f"{verb} user '{spec['username']}' -> group '{spec['group']}'")
            )

        self.stdout.write(self.style.NOTICE("Demo passwords are in the command source - rotate before production."))
