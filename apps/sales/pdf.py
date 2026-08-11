"""
Invoice PDF generation + storage (Day 8).

Requirement change: WeasyPrint needs GTK/Pango system libraries that are
unreliable on Windows. StockDesk therefore uses xhtml2pdf by default
(PRD allows WeasyPrint *or* xhtml2pdf). Set INVOICE_PDF_ENGINE=weasyprint
on Linux if those libs are installed.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string

from .models import Sale

logger = logging.getLogger("stockdesk.sales.pdf")


def invoice_context(sale: Sale) -> dict:
    sale = (
        Sale.objects.select_related("customer", "created_by")
        .prefetch_related("items__product")
        .get(pk=sale.pk)
    )
    return {
        "sale": sale,
        "company_name": getattr(settings, "COMPANY_NAME", "StockDesk"),
        "company_address": getattr(settings, "COMPANY_ADDRESS", ""),
        "company_phone": getattr(settings, "COMPANY_PHONE", ""),
        "company_gstin": getattr(settings, "COMPANY_GSTIN", ""),
    }


def render_invoice_html(sale: Sale) -> str:
    return render_to_string("sales/invoice_pdf.html", invoice_context(sale))


def html_to_pdf_bytes(html: str) -> bytes:
    engine = getattr(settings, "INVOICE_PDF_ENGINE", "xhtml2pdf").lower()
    if engine == "weasyprint":
        return _weasyprint_bytes(html)
    return _xhtml2pdf_bytes(html)


def _xhtml2pdf_bytes(html: str) -> bytes:
    from xhtml2pdf import pisa

    buffer = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")
    if result.err:
        raise RuntimeError("xhtml2pdf failed to render the invoice PDF.")
    return buffer.getvalue()


def _weasyprint_bytes(html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


def ensure_invoice_pdf(sale: Sale, *, force: bool = False) -> Sale:
    """
    Generate the invoice PDF and persist it on sale.pdf via Django's default
    storage backend (FileSystem in dev, S3 in prod).
    """
    if sale.pdf and not force:
        return sale

    pdf_bytes = html_to_pdf_bytes(render_invoice_html(sale))
    filename = Path(f"{sale.invoice_no.replace('/', '-')}.pdf").name

    if sale.pdf:
        sale.pdf.delete(save=False)

    sale.pdf.save(filename, ContentFile(pdf_bytes), save=True)
    logger.info("Stored invoice PDF for %s (%s bytes)", sale.invoice_no, len(pdf_bytes))
    return sale
