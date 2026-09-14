"""Standard/Online Promotions -> common normalized Promotions contract
mapping.

`raw` is intentionally typed as `object` and, internally, is accessed only
via duck-typed dict lookups (`.get()`), never a declared type. The dict
shape this code reads for Standard is now
chain_id/store_id/promotions[].{promotion_id, description, start_at,
end_at, is_gift_item, min_no_of_item_offered, groups[].{group_id,
discount_type, min_purchase_amount, items[].{item_code, <item economics>}}}
-- Promotion -> Group -> PromotionItem, mirroring real Standard XML's own
nesting. Online's shape is unchanged: promotions[].{..., items[].{item_code,
<identity facts>}}, no Group concept. Neither shape is a production parser
DTO or public API -- both are the same INTERNAL PROVISIONAL SEAM the
approved test suite's private `_standard_occurrence`/`_online_occurrence`
builders produce; when a real Promotions parser is designed, this internal
shape is expected to be reworked, not merely re-pointed.

Both entry points are occurrence-level and all-or-none: every promotion and
membership in `raw` is validated before anything is returned. If any
required identity/scope fact is absent (occurrence-level chain_id/store_id,
a promotion's promotion_id, an item's item_code) or `raw` itself is not
dict-shaped, `ValueError` is raised -- the established normalization-layer
convention already used by `normalize/rami_levy.py` and
`normalize/shufersal.py`'s `_require()` for a required-field contract
violation -- and no normalized promotion, group, or membership from that
occurrence is returned, even ones already found valid. Every other raw
value (opaque codes, non-boolean flags, unfamiliar RewardType/DiscountType
values, duplicate or missing raw GroupID, etc.) is preserved exactly as
supplied, with no coercion, parsing, validation, or derived economics --
GroupID is never used as structural identity or deduplication key; a
Standard Group's structural identity is its 0-based `group_index`, the
position it was encountered at within its Promotion's `groups` list.
"""

from __future__ import annotations

from datetime import datetime

from smartcart.normalize.promotion_contract import (
    NormalizedPromotion,
    NormalizedPromotionGroup,
    NormalizedPromotionMembership,
    OnlineMembershipFacts,
    OnlinePromotionFacts,
    StandardGroupFacts,
    StandardMembershipFacts,
    StandardPromotionFacts,
)


def _require_occurrence_scope(raw: object) -> tuple[dict[str, object], str, str]:
    if not isinstance(raw, dict):
        raise ValueError(
            "normalization contract violation: raw Promotions occurrence must be "
            f"dict-shaped, got {type(raw).__name__}"
        )
    chain_id = raw.get("chain_id")
    if chain_id is None:
        raise ValueError(
            "normalization contract violation: required occurrence field 'chain_id' was None"
        )
    store_id = raw.get("store_id")
    if store_id is None:
        raise ValueError(
            "normalization contract violation: required occurrence field 'store_id' was None"
        )
    return raw, chain_id, store_id


def normalize_standard_promotions_occurrence(
    raw: object,
    *,
    collected_at: datetime,
) -> tuple[
    list[NormalizedPromotion],
    list[NormalizedPromotionGroup],
    list[NormalizedPromotionMembership],
]:
    """Map one complete Standard-family Promotions occurrence (every
    promotion, group, and membership it contains) to the normalized
    contract."""
    occurrence, chain_id, store_id = _require_occurrence_scope(raw)

    raw_promotions = occurrence.get("promotions", [])
    if not isinstance(raw_promotions, list):
        raise ValueError(
            "normalization contract violation: occurrence field 'promotions' must be list-shaped"
        )

    promotions: list[NormalizedPromotion] = []
    groups: list[NormalizedPromotionGroup] = []
    memberships: list[NormalizedPromotionMembership] = []
    for promo in raw_promotions:
        promotion_id = promo.get("promotion_id")
        if promotion_id is None:
            raise ValueError(
                "normalization contract violation: required promotion field 'promotion_id' was None"
            )

        promotions.append(
            NormalizedPromotion(
                promotion_id_raw=promotion_id,
                retailer_chain_id=chain_id,
                store_id_raw=store_id,
                source_family="standard",
                description_raw=promo.get("description"),
                start_at_raw=promo.get("start_at"),
                end_at_raw=promo.get("end_at"),
                collected_at=collected_at,
                family_facts=StandardPromotionFacts(
                    is_gift_item_raw=promo.get("is_gift_item"),
                    min_no_of_item_offered_raw=promo.get("min_no_of_item_offered"),
                ),
            )
        )

        for group_index, group in enumerate(promo.get("groups", [])):
            groups.append(
                NormalizedPromotionGroup(
                    promotion_id_raw=promotion_id,
                    group_index=group_index,
                    family_facts=StandardGroupFacts(
                        group_id_raw=group.get("group_id"),
                        discount_type_raw=group.get("discount_type"),
                        min_purchase_amount_raw=group.get("min_purchase_amount"),
                    ),
                )
            )

            for item in group.get("items", []):
                item_code = item.get("item_code")
                if item_code is None:
                    raise ValueError(
                        "normalization contract violation: required membership field "
                        "'item_code' was None"
                    )
                memberships.append(
                    NormalizedPromotionMembership(
                        promotion_id_raw=promotion_id,
                        retailer_item_id_raw=item_code,
                        group_index=group_index,
                        family_facts=StandardMembershipFacts(
                            reward_type_raw=item.get("reward_type"),
                            discount_rate_raw=item.get("discount_rate"),
                            discounted_price_raw=item.get("discounted_price"),
                            min_qty_raw=item.get("min_qty"),
                            max_qty_raw=item.get("max_qty"),
                        ),
                    )
                )

    return promotions, groups, memberships


def normalize_online_promotions_occurrence(
    raw: object,
    *,
    collected_at: datetime,
) -> tuple[list[NormalizedPromotion], list[NormalizedPromotionMembership]]:
    """Map one complete Online-family Promotions occurrence (every
    promotion and membership it contains) to the normalized contract."""
    occurrence, chain_id, store_id = _require_occurrence_scope(raw)

    raw_promotions = occurrence.get("promotions", [])
    if not isinstance(raw_promotions, list):
        raise ValueError(
            "normalization contract violation: occurrence field 'promotions' must be list-shaped"
        )

    promotions: list[NormalizedPromotion] = []
    memberships: list[NormalizedPromotionMembership] = []
    for promo in raw_promotions:
        promotion_id = promo.get("promotion_id")
        if promotion_id is None:
            raise ValueError(
                "normalization contract violation: required promotion field 'promotion_id' was None"
            )

        promotions.append(
            NormalizedPromotion(
                promotion_id_raw=promotion_id,
                retailer_chain_id=chain_id,
                store_id_raw=store_id,
                source_family="online",
                description_raw=promo.get("description"),
                start_at_raw=promo.get("start_at"),
                end_at_raw=promo.get("end_at"),
                collected_at=collected_at,
                family_facts=OnlinePromotionFacts(
                    reward_type_raw=promo.get("reward_type"),
                    discount_type_raw=promo.get("discount_type"),
                    discount_rate_raw=promo.get("discount_rate"),
                    discounted_price_raw=promo.get("discounted_price"),
                    discounted_price_per_mida_raw=promo.get("discounted_price_per_mida"),
                    min_qty_raw=promo.get("min_qty"),
                    min_no_of_item_offered_raw=promo.get("min_no_of_item_offered"),
                    max_qty_raw=promo.get("max_qty"),
                ),
            )
        )

        for item in promo.get("items", []):
            item_code = item.get("item_code")
            if item_code is None:
                raise ValueError(
                    "normalization contract violation: required membership field "
                    "'item_code' was None"
                )
            memberships.append(
                NormalizedPromotionMembership(
                    promotion_id_raw=promotion_id,
                    retailer_item_id_raw=item_code,
                    group_index=None,
                    family_facts=OnlineMembershipFacts(
                        is_gift_item_raw=item.get("is_gift_item"),
                        item_type_raw=item.get("item_type"),
                    ),
                )
            )

    return promotions, memberships
