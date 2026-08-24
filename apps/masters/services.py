"""Product SKU allocation (locked sequence, no max(id)+1 races)."""

from __future__ import annotations

from django.db import IntegrityError, transaction

from .models import Product, SkuSequence

SKU_PREFIX = "SKU-"
SKU_WIDTH = 6
SKU_SEQUENCE_SLUG = "default"


def _max_existing_auto_sku_number() -> int:
    """Highest numeric suffix among SKUs like SKU-0001 / SKU-000001."""
    max_n = 0
    for sku in Product.objects.filter(sku__istartswith=SKU_PREFIX).values_list("sku", flat=True):
        suffix = sku[len(SKU_PREFIX) :]
        if suffix.isdigit():
            max_n = max(max_n, int(suffix))
    return max_n


def format_sku(number: int) -> str:
    return f"{SKU_PREFIX}{number:0{SKU_WIDTH}d}"


def peek_next_sku() -> str:
    """Preview of the next SKU without allocating it."""
    seq = SkuSequence.objects.filter(slug=SKU_SEQUENCE_SLUG).first()
    n = seq.last_number if seq else _max_existing_auto_sku_number()
    n += 1
    while Product.objects.filter(sku__iexact=format_sku(n)).exists():
        n += 1
    return format_sku(n)


@transaction.atomic
def next_sku() -> str:
    """
    Atomically allocate the next SKU.

    Must run inside a transaction (this function opens one). Locks the
    SkuSequence row with `select_for_update()`.
    """
    try:
        seq = SkuSequence.objects.select_for_update().get(slug=SKU_SEQUENCE_SLUG)
    except SkuSequence.DoesNotExist:
        try:
            SkuSequence.objects.create(
                slug=SKU_SEQUENCE_SLUG,
                last_number=_max_existing_auto_sku_number(),
            )
        except IntegrityError:
            pass
        seq = SkuSequence.objects.select_for_update().get(slug=SKU_SEQUENCE_SLUG)

    while True:
        seq.last_number += 1
        candidate = format_sku(seq.last_number)
        if not Product.objects.filter(sku__iexact=candidate).exists():
            seq.save(update_fields=["last_number"])
            return candidate
