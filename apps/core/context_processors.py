from django.conf import settings


def role_flags(request):
    """
    Exposes convenience role booleans to every template. These are used only
    to hide/show UI affordances — they must never be relied on for security;
    every view that needs enforcement uses PermissionRequiredMixin /
    UserPassesTestMixin server-side (see apps.core.mixins).
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "is_owner": False,
            "is_store_manager": False,
            "is_cashier": False,
            "company_name": settings.COMPANY_NAME,
        }

    group_names = set(user.groups.values_list("name", flat=True))
    return {
        "is_owner": user.is_superuser or "Owner" in group_names,
        "is_store_manager": "Store Manager" in group_names,
        "is_cashier": "Cashier" in group_names,
        "company_name": settings.COMPANY_NAME,
    }
