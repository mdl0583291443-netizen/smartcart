"""The common normalized price-item contract (frozen shape only).

This is a pure data-shape declaration: no validation, no methods beyond
what @dataclass generates by default, no defaults, and no transformation
logic. Field semantics are defined by the task's frozen normalized
contract, not by anything in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class NormalizedPriceItem:
    retailer_chain_id: str
    retailer_item_id: str
    store_id: str

    published_price: Decimal
    published_price_raw: str

    declared_quantity: Decimal
    declared_quantity_raw: str

    declared_quantity_unit_raw: str

    is_weighted: bool | None

    product_name: str

    collected_at: datetime
