"""
Server-side authorization enforcement for class-based views.

Per the PRD (Section 3): permissions must be enforced at the view layer and
the query layer — never by hiding UI elements alone. We use Django's own
Groups + PermissionRequiredMixin / UserPassesTestMixin exclusively; no
custom permission system.

Two complementary tools are provided:

- `PermissionRequiredMixin` — for fine-grained, per-model Django permissions
  (e.g. "masters.view_purchase_price"). Prefer this whenever the check maps
  to a real model-level permission.
- `GroupRequiredMixin` — for screen-level gating that maps directly to one
  of the three business roles (Owner / Store Manager / Cashier) and doesn't
  correspond to a single model permission.

Both mixins raise PermissionDenied (HTTP 403) for authenticated users who
lack access, and redirect to login for anonymous users — so an authorized
user editing a URL by hand gets a clean 403, not a silent redirect.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class PermissionRequiredMixin(LoginRequiredMixin, DjangoPermissionRequiredMixin):
    """LoginRequiredMixin + PermissionRequiredMixin, but 403s instead of redirecting once logged in."""

    raise_exception = True

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied


class GroupRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict a view to one or more of the three StockDesk roles. Superusers always pass."""

    allowed_groups = ()

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        return user.groups.filter(name__in=self.allowed_groups).exists()

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied
