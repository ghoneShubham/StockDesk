"""CSV download helpers for reports."""

from __future__ import annotations

import csv
from io import StringIO

from django.http import HttpResponse


def csv_response(filename: str, headers: list[str], rows) -> HttpResponse:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
