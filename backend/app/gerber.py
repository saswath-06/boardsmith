from __future__ import annotations

import zipfile
from pathlib import Path

from app.models import BoardLayout


def _coord(value_mm: float) -> str:
    """Convert mm to Gerber coordinate integer for FSLAX46Y46 format (4.6 = 4 int + 6 frac digits)."""
    return f"{int(round(value_mm * 1000000))}"


def _line(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"X{_coord(x1)}Y{_coord(y1)}D02*\nX{_coord(x2)}Y{_coord(y2)}D01*"


def _gerber_header(layer: str) -> str:
    return "\n".join(
        [
            "G04 Boardsmith demo Gerber*",
            f"G04 Layer: {layer}*",
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "%ADD10C,0.500*%",
            "%ADD13C,1.400*%",
            "D10*",
            "G01*",
        ]
    )


def write_gerber_zip(
    layout: BoardLayout,
    output_dir: Path,
    project_name: str,
    extra_files: dict[str, Path] | None = None,
) -> Path:
    gerber_dir = output_dir / "gerbers"
    gerber_dir.mkdir(parents=True, exist_ok=True)

    copper = [_gerber_header("F.Cu")]
    # Traces (drawn with 0.5mm line aperture D10)
    for trace in layout.traces:
        for a, b in zip(trace.points, trace.points[1:]):
            copper.append(_line(a[0], a[1], b[0], b[1]))
    # Pad flashes (1.4mm circular aperture D13)
    copper.append("D13*")
    for comp in layout.components:
        for pad in comp.pads:
            copper.append(f"X{_coord(pad.x)}Y{_coord(pad.y)}D03*")
    copper.append("M02*")
    (gerber_dir / f"{project_name}.F_Cu.gbr").write_text("\n".join(copper), encoding="utf-8")

    # F.Mask — pad openings (soldermask clearance), one flash per pad
    mask = [
        "G04 Boardsmith demo Gerber*",
        "G04 Layer: F.Mask*",
        "%FSLAX46Y46*%",
        "%MOMM*%",
        "%ADD11C,1.800*%",
        f"G04 Board {layout.width}mm x {layout.height}mm*",
        "D11*",
    ]
    for comp in layout.components:
        for pad in comp.pads:
            mask.append(f"X{_coord(pad.x)}Y{_coord(pad.y)}D03*")
    mask.append("M02*")
    (gerber_dir / f"{project_name}.F_Mask.gbr").write_text("\n".join(mask), encoding="utf-8")

    # F.SilkS — component outlines + ref-designator comments
    silkscreen = [
        "G04 Boardsmith demo Gerber*",
        "G04 Layer: F.SilkS*",
        "%FSLAX46Y46*%",
        "%MOMM*%",
        "%ADD12C,0.150*%",
        "D12*",
        "G01*",
    ]
    for comp in layout.components:
        silkscreen.append(f"G04 {comp.ref} {comp.label}*")
        lx = comp.x - comp.width / 2
        rx = comp.x + comp.width / 2
        ty = comp.y - comp.height / 2
        by = comp.y + comp.height / 2
        silkscreen.append(_line(lx, ty, rx, ty))  # top edge
        silkscreen.append(_line(rx, ty, rx, by))  # right edge
        silkscreen.append(_line(rx, by, lx, by))  # bottom edge
        silkscreen.append(_line(lx, by, lx, ty))  # left edge
    silkscreen.append("M02*")
    (gerber_dir / f"{project_name}.F_SilkS.gbr").write_text("\n".join(silkscreen), encoding="utf-8")

    edge = [
        _gerber_header("Edge.Cuts"),
        _line(0, 0, layout.width, 0),
        _line(layout.width, 0, layout.width, layout.height),
        _line(layout.width, layout.height, 0, layout.height),
        _line(0, layout.height, 0, 0),
        "M02*",
    ]
    (gerber_dir / f"{project_name}.Edge_Cuts.gbr").write_text("\n".join(edge), encoding="utf-8")

    drill_lines = ["M48", "METRIC,TZ", "T01C0.800", "%", "T01"]
    for comp in layout.components:
        for pad in comp.pads:
            drill_lines.append(f"X{pad.x:.4f}Y{pad.y:.4f}")
    drill_lines.append("M30")
    (gerber_dir / f"{project_name}.drl").write_text("\n".join(drill_lines), encoding="utf-8")

    readme = (
        "Boardsmith manufacturing bundle.\n"
        "\n"
        "Contents:\n"
        "  *.gbr        — Gerber RS-274X copper / mask / silk / edge layers\n"
        "  *.drl        — Excellon drill file\n"
        "  *_BOM.csv    — Engineering bill of materials with prices\n"
        "  *_BOM_JLCPCB.csv — JLCPCB SMT-assembly upload format\n"
        "  *_CPL.csv    — Pick-and-place file (Designator, Mid X/Y, Layer, Rotation)\n"
        "\n"
        "Upload all three CSVs alongside the Gerber files when ordering SMT\n"
        "assembly from JLCPCB. Run DRC/CAM review in KiCad before fabrication.\n"
    )
    (gerber_dir / "README.txt").write_text(readme, encoding="utf-8")

    zip_path = output_dir / f"{project_name}_manufacturing_bundle.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(gerber_dir.iterdir()):
            archive.write(path, arcname=path.name)
        # Drop in BOMs / CPL alongside the Gerber layers so the downloaded
        # bundle is everything a user needs to upload to JLCPCB.
        for arcname, src in (extra_files or {}).items():
            if src.exists():
                archive.write(src, arcname=arcname)
    return zip_path
