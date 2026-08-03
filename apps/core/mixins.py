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
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


class PermissionRequiredMixin(LoginRequiredMixin, DjangoPermissionRequiredMixin):
    """
    Authenticated users without the permission get HTTP 403.
    Anonymous users are redirected to login (Django's raise_exception=True
    would otherwise 403 guests too — we want the login redirect instead).
    """

    raise_exception = True

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied(self.get_permission_denied_message())


class GroupRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict a view to one or more of the three StockDesk roles. Superusers always pass."""

    allowed_groups = ()
    raise_exception = True

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        return user.groups.filter(name__in=self.allowed_groups).exists()

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied(self.get_permission_denied_message())
