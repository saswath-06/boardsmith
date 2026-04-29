"""Pick-and-place (CPL) CSV export in JLCPCB SMT-assembly format.

JLCPCB's expected columns are: Designator, Mid X, Mid Y, Layer, Rotation.
Coordinates are the geometric center of each component in millimeters
relative to the board origin (bottom-left corner).

Only top-side components are emitted — Boardsmith doesn't currently
generate bottom-side placements. Through-hole modules (ESP32, Arduino
Nano, etc.) are still listed so a manual placement engineer can find
them, but JLCPCB will skip them automatically during SMT.

Reference docs:
  https://jlcpcb.com/help/article/444-Surface-Mount-Assembly-File
"""
from __future__ import annotations

import csv
from pathlib import Path

from app.models import BoardLayout


def write_cpl_csv(layout: BoardLayout, path: Path) -> Path:
    """Write the layout's component placements as a JLCPCB-format CPL CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Sort by reference for stable, human-scannable output (R1, R2, …, U1, …).
    rows = sorted(layout.components, key=_natural_ref_key)

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for comp in rows:
            writer.writerow(
                [
                    comp.ref,
                    f"{comp.x:.4f}mm",
                    f"{comp.y:.4f}mm",
                    "Top",
                    f"{comp.rotation:.0f}",
                ]
            )
    return path


def _natural_ref_key(comp) -> tuple[str, int]:  # type: ignore[no-untyped-def]
    import re

    match = re.match(r"^([A-Za-z]+)(\d+)", comp.ref or "")
    if not match:
        return (comp.ref or "", 0)
    prefix, number = match.groups()
    return (prefix, int(number))
