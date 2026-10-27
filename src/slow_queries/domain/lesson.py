"""The lesson as data: which index each step adds and which plans are read before and after it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IndexStep:
    """One change: apply migration `number`, then read the plans named in `captures`."""

    number: int
    label: str
    captures: tuple[str, ...]


INDEX_NAMES = ("idx_orders_created_at", "idx_orders_customer_created", "idx_orders_listing")

#: Plans read with only the primary key in place.
BEFORE_ANY_INDEX = (
    "q1_day_before",
    "q2_latest_whale_before",
    "q2_latest_small_before",
    "q3_toast_wide",
    "q3_toast_narrow",
)

STEPS = (
    IndexStep(1, "+ idx_orders_created_at", ("q1_day_after",)),
    IndexStep(
        2,
        "+ idx_orders_customer_created",
        ("q2_latest_whale_after", "q2_latest_small_after", "q3_listing_before", "q3_listing_narrow"),
    ),
    IndexStep(3, "+ idx_orders_listing", ("q3_listing_after",)),
    IndexStep(4, "idx_orders_listing only (idx_orders_customer_created dropped)", ()),
)

#: (label, plan before, plan after) rows of the comparison table.
COMPARISONS = (
    ("q1 day query", "q1_day_before", "q1_day_after"),
    ("q2 latest 10, heavy customer", "q2_latest_whale_before", "q2_latest_whale_after"),
    ("q2 latest 10, small customer", "q2_latest_small_before", "q2_latest_small_after"),
    ("q3 listing: SELECT * vs covering index", "q3_listing_before", "q3_listing_after"),
    ("q3 listing: five columns, no covering index", "q3_listing_before", "q3_listing_narrow"),
    ("q3 TOAST demo: SELECT * vs without the note", "q3_toast_wide", "q3_toast_narrow"),
)
