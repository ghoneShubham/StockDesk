from django.db import models


class ReportPermissions(models.Model):
    """
    Not a real table — a permission-only marker model. Django permissions
    must attach to a content type, but "financial report" and "operational
    report" aren't single database models; this gives them a home so they
    can be assigned to Groups and checked with PermissionRequiredMixin like
    any other permission.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_financial_reports", "Can view financial reports (margin, valuation, P&L)"),
            ("view_operational_reports", "Can view operational reports (stock, low stock)"),
        ]
