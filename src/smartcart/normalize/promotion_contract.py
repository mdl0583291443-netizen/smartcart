"""The common normalized Promotions contract (frozen shape only).

Pure data-shape declarations: no validation, no methods beyond what
@dataclass generates by default, no defaults, and no transformation logic --
mirrors the role `contract.py` plays for `NormalizedPriceItem`. Field
semantics are defined by the frozen Promotions Stage-1 requirements, not by
anything in this module.

Standard and Online source families are structurally different (see the
Promotions structural/semantic recon this contract transcribes): Standard
carries promotion economics at the membership (PromotionItem) level, with
only a gift-item flag at the promotion level; Online carries economics at
the promotion level itself, with membership limited to identity/gift/type
facts. `family_facts` is a plain type union (`StandardPromotionFacts |
OnlinePromotionFacts`), not a shared base class with nullable fields for
both families -- the same non-merging approach already used for Rami Levy's
two PriceFull schema families (see collectors/rami_levy/records.py).

One promotion may cover many SKUs; one SKU may participate in many
promotions. `NormalizedPromotion` and `NormalizedPromotionMembership` are
therefore two separate normalized records, joined by `promotion_id_raw` --
never flattened into one per-item record carrying duplicated promotion-level
facts.

Every field ending in `_raw` is a source-faithful, unprocessed value:
preserved exactly as the retailer published it, no numeric coercion, no
enum/boolean interpretation, no unit conversion, no derived economics.
Unlike `NormalizedPriceItem`, no typed (non-`_raw`) counterpart exists for
any promotion economic field in this v1 contract -- that pairing was not
part of what Stage-1 recon evidence froze, and inventing one now would be a
new design decision, not a transcription of it.

`ClubID`/`AdditionalIsCoupon`-equivalent facts are deliberately absent from
this contract: their exact source structural placement (Promotion vs.
Group vs. PromotionItem level, in either family) was not evidenced by the
targeted structural-placement check that preceded this skeleton. No
placeholder/nullable field is added for them -- they remain out of the
normalized contract until that evidence exists.

Note on asymmetry: `NormalizedPromotion` carries a `source_family`
discriminator; `NormalizedPromotionMembership` deliberately does not -- its
family is determined structurally, by which `family_facts` type it holds
(the same style already used by `parse.schema_family_of()` for PriceFull:
family identity comes from the shape actually present, not from a stored
tag). This mirrors the frozen field lists exactly as specified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class StandardPromotionFacts:
    """Promotion-level facts specific to the Standard source family.

    Standard-family promotion economics live at the membership
    (PromotionItem) level, not here -- see `StandardMembershipFacts`. At
    the promotion level, only the gift-item flag was evidenced.
    """

    is_gift_item_raw: str | None


@dataclass(frozen=True)
class OnlinePromotionFacts:
    """Promotion-level facts specific to the Online source family.

    Unlike Standard, Online-family promotion economics were evidenced at
    the promotion level itself. Every field here is a raw source value --
    no effective price, savings, eligibility, or interpreted RewardType is
    derived.
    """

    reward_type_raw: str | None
    discount_type_raw: str | None
    discount_rate_raw: str | None
    discounted_price_raw: str | None
    discounted_price_per_mida_raw: str | None
    min_qty_raw: str | None
    min_no_of_item_offered_raw: str | None
    max_qty_raw: str | None


@dataclass(frozen=True)
class NormalizedPromotion:
    """One promotion, shared facts plus its source-family-specific facts.

    `store_id_raw` is intentionally named with the `_raw` suffix (unlike
    `NormalizedPriceItem.store_id`): a promotion's store scope is preserved
    exactly as the source represents it, without assuming every promotion
    source declares a single definite store the way a PriceFull item does.
    It is required (`str`, not `str | None`): a missing occurrence store
    scope is a whole-occurrence failure, so a successfully normalized
    promotion must never represent `store_id_raw=None` -- that validation
    is not implemented yet, but the type already forbids the value it would
    reject.

    `collected_at` is caller-owned context, not derived from parsed source
    content -- consistent with `NormalizedPriceItem.collected_at` already
    being caller-supplied. Occurrence provenance (e.g. an occurrence id) is
    deliberately NOT a field here: it remains caller/integration-seam
    context, the same boundary already established for `NormalizedPriceItem`
    by ADR-0011 (no occurrence-context fields on the normalized item itself).
    """

    promotion_id_raw: str
    retailer_chain_id: str
    store_id_raw: str
    source_family: Literal["standard", "online"]
    description_raw: str | None
    start_at_raw: str | None
    end_at_raw: str | None
    collected_at: datetime
    family_facts: StandardPromotionFacts | OnlinePromotionFacts


@dataclass(frozen=True)
class StandardMembershipFacts:
    """Membership (PromotionItem)-level facts specific to the Standard
    source family -- this is where Standard-family promotion economics
    were evidenced to live, not at the promotion level."""

    reward_type_raw: str | None
    discount_rate_raw: str | None
    discounted_price_raw: str | None
    min_qty_raw: str | None
    min_no_of_item_offered_raw: str | None
    max_qty_raw: str | None


@dataclass(frozen=True)
class OnlineMembershipFacts:
    """Membership-level facts specific to the Online source family.

    Online-family membership carries identity/gift/type facts only --
    economics live at the promotion level (`OnlinePromotionFacts`), not
    here.
    """

    is_gift_item_raw: str | None
    item_type_raw: str | None


@dataclass(frozen=True)
class NormalizedPromotionMembership:
    """One SKU's membership in one promotion, shared facts plus its
    source-family-specific facts.

    Joined to its `NormalizedPromotion` by `promotion_id_raw`. One
    promotion may have many memberships; one SKU (`retailer_item_id_raw`)
    may appear in many promotions' memberships -- never merged or
    deduplicated here.
    """

    promotion_id_raw: str
    retailer_item_id_raw: str
    family_facts: StandardMembershipFacts | OnlineMembershipFacts
