"""JLCPCB all-in build cost estimator.

Approximates JLCPCB's published pricing for a small 2-layer green
soldermask PCB with SMT assembly. Numbers are deliberately
conservative so the demo never undersells the real-world cost; they
match the order summary you see at checkout for a 100x100mm 2-layer
board with one-side assembly as of mid-2026.

Pricing levers:
- ``pcb_fab_usd`` — board fabrication. Tiered lookup against typical
  100x100mm 2-layer prices.
- ``smt_setup_usd`` — flat one-time engineering fee per assembly side.
- ``smt_placement_usd`` — per-joint placement charge. JLCPCB advertises
  $0.0017/joint for "Standard Component" placements.
- ``stencil_usd`` — required for any SMT order; flat $8.
- ``shipping_usd`` — DHL economy estimate. We don't have address-aware
  pricing, so a flat $5 keeps the math honest without hiding the cost.
"""
from __future__ import annotations

from typing import TypedDict

# JLCPCB 2-layer 100x100mm green soldermask, qty -> board fab cost (USD).
# Below 5 boards JLCPCB still charges the 5-board minimum; above 100
# the per-board cost flattens out at roughly $0.25.
_PCB_FAB_TIERS: dict[int, float] = {
    5: 2.00,
    30: 8.00,
    100: 25.00,
}

_DEFAULT_TIERS: tuple[int, ...] = (5, 30, 100)

# JLCPCB published rates (mid-2026).
_SMT_SETUP_USD = 8.00          # one-time per order, single-sided assembly
_SMT_PLACEMENT_PER_JOINT = 0.0017
_STENCIL_USD = 8.00            # SMT orders require a stencil
_SHIPPING_USD = 5.00           # DHL economy flat estimate
_SCRAP_BUFFER = 1.05           # 5% extra components for assembly scrap


class CostEstimate(TypedDict):
    """Single-tier cost breakdown. Mirrored on the frontend."""

    qty: int
    parts: float
    pcb_fab: float
    smt_setup: float
    smt_placement: float
    stencil: float
    shipping: float
    total: float
    smt_joints: int


def _round(value: float) -> float:
    return round(value + 1e-9, 2)


def compute_jlcpcb_estimate(
    parts_unit_cost_usd: float,
    smt_joints: int,
    qty: int,
) -> CostEstimate:
    """Build the per-tier all-in estimate.

    ``parts_unit_cost_usd`` is the BOM total for one board (sum of
    extended_price_usd over all priced lines). ``smt_joints`` is the
    total pad count across SMT components on the board.
    """
    qty = max(int(qty), 1)
    parts_total = parts_unit_cost_usd * qty * _SCRAP_BUFFER

    # PCB fab: pick the closest tier at or above qty; clamp to the highest
    # known tier when qty is bigger than 100.
    fab_qty = next((t for t in _DEFAULT_TIERS if qty <= t), _DEFAULT_TIERS[-1])
    pcb_fab = _PCB_FAB_TIERS[fab_qty]

    has_smt = smt_joints > 0
    smt_setup = _SMT_SETUP_USD if has_smt else 0.0
    smt_placement = smt_joints * qty * _SMT_PLACEMENT_PER_JOINT if has_smt else 0.0
    stencil = _STENCIL_USD if has_smt else 0.0

    total = parts_total + pcb_fab + smt_setup + smt_placement + stencil + _SHIPPING_USD

    return CostEstimate(
        qty=qty,
        parts=_round(parts_total),
        pcb_fab=_round(pcb_fab),
        smt_setup=_round(smt_setup),
        smt_placement=_round(smt_placement),
        stencil=_round(stencil),
        shipping=_round(_SHIPPING_USD),
        total=_round(total),
        smt_joints=smt_joints,
    )


def compute_estimate_tiers(
    parts_unit_cost_usd: float,
    smt_joints: int,
    tiers: tuple[int, ...] = _DEFAULT_TIERS,
) -> list[CostEstimate]:
    """Build estimates for the standard 5/30/100 tiers."""
    return [
        compute_jlcpcb_estimate(parts_unit_cost_usd, smt_joints, qty)
        for qty in tiers
    ]
