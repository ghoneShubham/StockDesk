"""
Central place for the three role names used across StockDesk.

These map 1:1 to Django Groups created by the `bootstrap_roles` management
command (apps/accounts/management/commands/bootstrap_roles.py). Views must
never hardcode the string again — import from here instead.
"""

OWNER = "Owner"
STORE_MANAGER = "Store Manager"
CASHIER = "Cashier"

ALL_ROLES = (OWNER, STORE_MANAGER, CASHIER)
