"""Bill of Materials extraction and CSV export.

Groups identical components from a CircuitDesign into BOM lines and writes
both an engineering CSV (Reference, Qty, Value, …) and the JLCPCB-formatted
CSV used when uploading for SMT assembly.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from app.component_library import COMPONENT_LIBRARY, normalize_component_type
from app.cost import compute_estimate_tiers
from app.lcsc import lookup_lcsc, lookup_unit_price_usd
from app.models import BomData, BomLine, CircuitDesign, CostEstimate


def _natural_ref_key(ref: str) -> tuple[str, int, str]:
    """Sort references like R1, R2, R10 numerically rather than lexically."""
    match = re.match(r"^([A-Za-z]+)(\d+)(.*)$", ref or "")
    if not match:
        return (ref or "", 0, "")
    prefix, number, tail = match.groups()
    return (prefix, int(number), tail)


def _normalize_value(value: str | None) -> str:
    """Canonicalize values like '10K', '10k', '10 kΩ' → '10k' for grouping."""
    if value is None:
        return ""
    s = str(value).strip()
    s = s.replace("Ω", "").replace("ohm", "").replace("OHM", "")
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _describe(comp_type: str, value: str | None) -> str:
    """Human-readable description for a BOM row."""
    normalized = normalize_component_type(comp_type)
    library = COMPONENT_LIBRARY.get(normalized) if normalized else None
    base = library.display_name if library else comp_type
    if value:
        return f"{base} — {value}"
    return base


def _package_for(comp_type: str) -> str | None:
    normalized = normalize_component_type(comp_type)
    library = COMPONENT_LIBRARY.get(normalized) if normalized else None
    if not library:
        return None
    # Footprint strings look like "Resistor_SMD:R_0805_2012Metric" — return
    # the bit after the colon for compactness in the BOM table.
    fp = library.footprint
    return fp.split(":", 1)[1] if ":" in fp else fp


def _category_for(comp_type: str) -> str:
    normalized = normalize_component_type(comp_type)
    library = COMPONENT_LIBRARY.get(normalized) if normalized else None
    return library.category if library else "other"


def _smt_joints_for(comp_type: str) -> int:
    """Pad count if this part is SMT-assembled by JLCPCB, else 0.

    Through-hole connectors/headers and dev modules don't get the
    per-joint placement fee — they're hand-soldered or pre-assembled.
    """
    normalized = normalize_component_type(comp_type)
    library = COMPONENT_LIBRARY.get(normalized) if normalized else None
    if not library:
        return 0
    fp = library.footprint
    if fp.startswith("Module:") or fp.startswith("Sensor:"):
        return 0
    if "PinHeader" in fp or "JST_XH" in fp:
        return 0
    if "_SMD" in fp or "SOT-" in fp or "USB_C_Receptacle" in fp:
        return len(library.pins)
    return 0


def build_bom(design: CircuitDesign) -> BomData:
    """Group ``design.components`` into BOM lines."""
    # Group by canonical (type, value) — components with same type and value
    # are interchangeable parts.
    groups: dict[tuple[str, str], list] = {}
    raw_values: dict[tuple[str, str], str | None] = {}
    notes_map: dict[tuple[str, str], str | None] = {}

    for comp in design.components:
        norm_type = normalize_component_type(comp.type) or comp.type
        key = (norm_type, _normalize_value(comp.value))
        groups.setdefault(key, []).append(comp.ref)
        # Keep the first non-empty raw value as the displayed one.
        if raw_values.get(key) is None and comp.value:
            raw_values[key] = comp.value
        # Preserve any notes on the first component in the group.
        if notes_map.get(key) is None and comp.notes:
            notes_map[key] = comp.notes

    lines: list[BomLine] = []
    # Sort groups for stable BOM ordering: by category then type then value.
    sorted_keys = sorted(
        groups.keys(),
        key=lambda k: (
            _CATEGORY_ORDER.get(_category_for(k[0]), 99),
            k[0].lower(),
            k[1],
        ),
    )
    for idx, key in enumerate(sorted_keys, start=1):
        comp_type, _ = key
        refs = sorted(groups[key], key=_natural_ref_key)
        raw_value = raw_values.get(key)
        package = _package_for(comp_type)
        lcsc = lookup_lcsc(comp_type, raw_value, package)
        unit_price = lookup_unit_price_usd(
            comp_type, lcsc.lcsc_part_number if lcsc else None
        )
        ext_price = (
            round(unit_price * len(refs), 4) if unit_price is not None else None
        )
        lines.append(
            BomLine(
                line_id=idx,
                references=refs,
                quantity=len(refs),
                type=comp_type,
                value=raw_value,
                description=_describe(comp_type, raw_value),
                package=package,
                category=_category_for(comp_type),
                notes=notes_map.get(key),
                lcsc_part_number=lcsc.lcsc_part_number if lcsc else None,
                manufacturer_pn=lcsc.manufacturer_pn if lcsc else None,
                manufacturer=lcsc.manufacturer if lcsc else None,
                unit_price_usd=unit_price,
                extended_price_usd=ext_price,
            )
        )

    total_quantity = sum(line.quantity for line in lines)
    priced = [ln for ln in lines if ln.extended_price_usd is not None]
    total_unit_cost = round(sum(ln.extended_price_usd or 0.0 for ln in priced), 2)

    # SMT joints across the BOM = sum of (pads * quantity) for SMT parts.
    smt_joints = sum(
        _smt_joints_for(line.type) * line.quantity for line in lines
    )

    estimates = [
        CostEstimate(**est)
        for est in compute_estimate_tiers(total_unit_cost, smt_joints)
    ]

    return BomData(
        project_name=design.project_name,
        lines=lines,
        total_unique=len(lines),
        total_quantity=total_quantity,
        total_unit_cost_usd=total_unit_cost,
        priced_line_count=len(priced),
        currency="USD",
        smt_joints=smt_joints,
        cost_estimates=estimates,
    )


_CATEGORY_ORDER = {
    "microcontroller": 0,
    "sensor": 1,
    "power": 2,
    "discrete": 3,
    "passive": 4,
    "connector": 5,
    "other": 9,
}


def write_bom_csv(bom: BomData, path: Path) -> Path:
    """Engineering-style BOM CSV (one row per line item, refs comma-joined)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "Item",
                "References",
                "Quantity",
                "Value",
                "Type",
                "Description",
                "Package",
                "LCSC #",
                "MFR P/N",
                "Manufacturer",
                "Unit Price (USD)",
                "Extended Price (USD)",
                "Notes",
            ]
        )
        for line in bom.lines:
            writer.writerow(
                [
                    line.line_id,
                    ", ".join(line.references),
                    line.quantity,
                    line.value or "",
                    line.type,
                    line.description,
                    line.package or "",
                    line.lcsc_part_number or "",
                    line.manufacturer_pn or "",
                    line.manufacturer or "",
                    f"{line.unit_price_usd:.4f}" if line.unit_price_usd is not None else "",
                    f"{line.extended_price_usd:.4f}" if line.extended_price_usd is not None else "",
                    line.notes or "",
                ]
            )
        # Footer total — blank line then a TOTAL row.
        writer.writerow([])
        writer.writerow(
            [
                "",
                "",
                bom.total_quantity,
                "",
                "",
                f"TOTAL ({bom.priced_line_count}/{bom.total_unique} lines priced)",
                "",
                "",
                "",
                "",
                "",
                f"{bom.total_unit_cost_usd:.2f}",
                "",
            ]
        )
    return path


def write_jlcpcb_csv(bom: BomData, path: Path) -> Path:
    """JLCPCB SMT assembly upload format.

    Column order matches the template at
    https://jlcpcb.com/help/article/96-bom-file (Comment, Designator,
    Footprint, LCSC Part #).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for line in bom.lines:
            comment = (
                f"{line.value} {line.type}".strip() if line.value else line.type
            )
            writer.writerow(
                [
                    comment,
                    ",".join(line.references),
                    line.package or "",
                    line.lcsc_part_number or "",
                ]
            )
    return path


def bom_to_csv_string(bom: BomData) -> str:
    """In-memory CSV (used for tests / inline previews)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Item", "References", "Quantity", "Value", "Description"])
    for line in bom.lines:
        writer.writerow(
            [
                line.line_id,
                ", ".join(line.references),
                line.quantity,
                line.value or "",
                line.description,
            ]
        )
    return buf.getvalue()
