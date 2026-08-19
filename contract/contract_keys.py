"""Declared key set. Bright Data OMITS absent keys rather than nulling them,
so every consumer runs row.get(k, MISSING) over this list. A key that is absent
is not an error and is not a zero: it renders as MISSING."""

MISSING = "∅MISSING"

CONTRACT_KEYS = [
    "name", "model", "gtin", "hazard",
    "source.authority", "source.ref", "source.published", "source.url",
    "days", "tier", "found_by_query",
    "arms.US", "arms.DE", "arms.IN",
    "evidence.captured_at", "evidence.http", "evidence.viewport",
    "evidence.assertion.needle", "evidence.assertion.dom_path", "evidence.assertion.context",
    "evidence.buy_control.present", "evidence.buy_control.label",
    "evidence.buy_control.in_stock", "evidence.buy_control.ships_from",
    "evidence.currency", "evidence.sha256", "evidence.trace", "evidence.job_id",
]
