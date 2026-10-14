"""Reference-safe product variant lifecycle operations."""

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.money import money
from app.models.product import ProductVariant


class VariantLifecycleError(ValueError):
    """Raised when a variant update would violate stable identity rules."""


def _variant_payload(raw: Any) -> dict:
    if hasattr(raw, "model_dump"):
        return raw.model_dump(exclude_unset=True)
    return dict(raw)


def reconcile_product_variants(
    db: Session,
    product_id: UUID,
    variants_data: Iterable[Any],
) -> list[ProductVariant]:
    """Update/create/archive variants without deleting referenced identities."""
    payloads = [_variant_payload(item) for item in variants_data]
    if not payloads:
        raise VariantLifecycleError("A product must retain at least one active variant")

    existing = (
        db.query(ProductVariant)
        .filter(ProductVariant.product_id == product_id)
        .order_by(ProductVariant.created_at, ProductVariant.id)
        .with_for_update()
        .all()
    )
    by_id = {str(variant.id): variant for variant in existing}
    by_sku = {variant.sku: variant for variant in existing if variant.sku}
    used_ids: set[UUID] = set()
    active_variants: list[ProductVariant] = []

    for payload in payloads:
        requested_id = payload.pop("id", None)
        sku = (payload.get("sku") or "").strip() or None
        attributes = payload.get("attributes") or {}

        variant = None
        if requested_id is not None:
            variant = by_id.get(str(requested_id))
            if variant is None:
                raise VariantLifecycleError(
                    f"Variant {requested_id} does not belong to product {product_id}"
                )
        elif sku is not None:
            variant = by_sku.get(sku)
        else:
            variant = next(
                (
                    candidate
                    for candidate in existing
                    if candidate.id not in used_ids
                    and candidate.sku is None
                    and (candidate.attributes or {}) == attributes
                ),
                None,
            )

        if variant is not None and variant.id in used_ids:
            raise VariantLifecycleError("A variant identity appears more than once in the update")

        if sku is not None:
            conflicting = (
                db.query(ProductVariant)
                .filter(
                    ProductVariant.sku == sku,
                    ProductVariant.product_id != product_id,
                )
                .first()
            )
            if conflicting is not None:
                raise VariantLifecycleError(f"SKU '{sku}' is already assigned to another product")

        quantity = int(payload.get("quantity_in_stock", 1))
        if quantity < 0:
            raise VariantLifecycleError("Variant stock cannot be negative")

        if variant is None:
            variant = ProductVariant(product_id=product_id)
            db.add(variant)
            db.flush()
            existing.append(variant)

        variant.sku = sku
        variant.attributes = attributes
        variant.price_adjustment = money(payload.get("price_adjustment", 0))
        variant.quantity_in_stock = quantity
        variant.is_active = True
        variant.archived_at = None
        used_ids.add(variant.id)
        active_variants.append(variant)

    archived_at = datetime.now(timezone.utc)
    for variant in existing:
        if variant.id not in used_ids and variant.is_active:
            variant.is_active = False
            variant.archived_at = archived_at
            variant.quantity_in_stock = 0

    db.flush()
    return active_variants
