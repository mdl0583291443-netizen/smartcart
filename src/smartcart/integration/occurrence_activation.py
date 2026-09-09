"""Normalize -> persistence integration seam: occurrence/batch-scoped glue
between already-normalized NormalizedPriceItems and the existing, unchanged
catalog/activation engine. Resolves the batch's store once (via
catalog.get_or_create_store_by_alias) and delegates the whole mapped batch
to activate_occurrence in one call; owns no idempotency, retry, or
transaction logic of its own -- that remains activate_occurrence's alone."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pg8000.native

from smartcart.db_spike.activation import (
    ActivationOutcome,
    NormalizedActivationItem,
    activate_occurrence,
)
from smartcart.db_spike.catalog import get_or_create_store_by_alias
from smartcart.normalize.contract import NormalizedPriceItem


@dataclass(frozen=True)
class StoreResolutionContext:
    occurrence_id: int
    subchain_id: str
    source: str
    alias_context: str


def activate_normalized_occurrence(
    conn: pg8000.native.Connection,
    *,
    context: StoreResolutionContext,
    items: Sequence[NormalizedPriceItem],
    on_checkpoint: Callable[[str, int], None] | None = None,
) -> ActivationOutcome:
    if not items:
        raise ValueError("activate_normalized_occurrence requires at least one item.")

    first = items[0]
    for item in items[1:]:
        if item.retailer_chain_id != first.retailer_chain_id:
            raise ValueError(
                f"NormalizedPriceItem.retailer_chain_id {item.retailer_chain_id!r} "
                f"disagrees with the batch's common value {first.retailer_chain_id!r}."
            )
        if item.store_id != first.store_id:
            raise ValueError(
                f"NormalizedPriceItem.store_id {item.store_id!r} disagrees with "
                f"the batch's common value {first.store_id!r}."
            )
        if item.collected_at != first.collected_at:
            raise ValueError(
                f"NormalizedPriceItem.collected_at {item.collected_at!r} disagrees "
                f"with the batch's common value {first.collected_at!r}."
            )

    resolved_store_id = get_or_create_store_by_alias(
        conn,
        chain_id=first.retailer_chain_id,
        subchain_id=context.subchain_id,
        source=context.source,
        alias_context=context.alias_context,
        raw_value=first.store_id,
    )

    normalized_items = [
        NormalizedActivationItem(
            retailer_chain_id=item.retailer_chain_id,
            resolved_store_id=resolved_store_id,
            item_code_raw=item.retailer_item_id,
            price=item.published_price,
            price_raw=item.published_price_raw,
            product_name=item.product_name,
            declared_quantity=item.declared_quantity,
            declared_quantity_raw=item.declared_quantity_raw,
            declared_quantity_unit_raw=item.declared_quantity_unit_raw,
            is_weighted=item.is_weighted,
            collected_at=item.collected_at,
        )
        for item in items
    ]

    return activate_occurrence(
        conn,
        occurrence_id=context.occurrence_id,
        products=[],
        normalized_items=normalized_items,
        on_checkpoint=on_checkpoint,
    )
