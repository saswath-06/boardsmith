from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.bom import build_bom, write_bom_csv, write_jlcpcb_csv
from app.gerber import write_gerber_zip
from app.kicad_writer import write_kicad_schematic
from app.llm import (
    fallback_design,
    parse_circuit_description,
    refine_circuit_design,
)
from app.models import BoardLayout, BomData, CircuitDesign, PipelineEvent, StageStatus
from app.pcb_layout import generate_layout, layout_svg, route_layout
from app.pin_aliases import normalize_design
from app.schematic import write_schematic_svg
from app.storage import STORE, JobRecord


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "Boardsmith_Demo"


async def _emit(job_id: str, stage: str, status: StageStatus, message: str, data: Any = None) -> None:
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    elif isinstance(data, list):
        data = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in data]
    await STORE.add_event(job_id, PipelineEvent(stage=stage, status=status, data=data, message=message))


async def _safe_stage(
    job: JobRecord,
    stage: str,
    running_message: str,
    complete_message: str,
    action: Callable[[], Awaitable[Any]],
    fallback: Callable[[Exception], Any],
) -> Any:
    await _emit(job.job_id, stage, StageStatus.running, running_message)
    try:
        result = await action()
        await _emit(job.job_id, stage, StageStatus.complete, complete_message, result)
        return result
    except Exception as exc:  # noqa: BLE001
        result = fallback(exc)
        await _emit(job.job_id, stage, StageStatus.error, f"Warning: {exc}. Continuing with fallback.", result)
        return result


def _persist_design(job: JobRecord, design: CircuitDesign) -> CircuitDesign:
    """Normalize pin aliases, write circuit.json, register the artifact."""
    design = normalize_design(design)
    path = job.output_dir / "circuit.json"
    path.write_text(json.dumps(design.model_dump(mode="json"), indent=2), encoding="utf-8")
    STORE.add_artifact(job.job_id, "circuit_json", path)
    return design


async def run_pipeline(job: JobRecord) -> None:
    """Initial generation pipeline: parse → schematic → PCB → routing → 3D → Gerber."""
    try:
        design = await _safe_stage(
            job,
            "parse",
            "Parsing natural language into supported components and nets.",
            "Circuit JSON generated.",
            lambda: _async_value(parse_circuit_description(job.description)),
            lambda exc: fallback_design(job.description, str(exc)),
        )
        design = _persist_design(job, design)
        if design.warnings:
            await _emit(job.job_id, "parse", StageStatus.error, "Warning: parser used assumptions.", {"warnings": design.warnings})
        await _run_downstream(job, design)
    except Exception as exc:  # noqa: BLE001
        await _emit(job.job_id, "pipeline", StageStatus.error, f"Unexpected pipeline warning: {exc}", None)
    finally:
        await STORE.finish(job.job_id)


async def run_refinement_pipeline(job: JobRecord, parent_design: CircuitDesign) -> None:
    """Refinement pipeline: refine(parent_design, instruction) → same downstream stages."""
    instruction = job.instruction or job.description
    try:
        design = await _safe_stage(
            job,
            "parse",
            f"Refining existing design: {instruction}",
            "Refined circuit JSON generated.",
            lambda: _async_value(refine_circuit_design(parent_design, instruction)),
            lambda exc: parent_design.model_copy(update={
                "warnings": [*parent_design.warnings, f"refinement failed — kept previous ({exc})"],
            }),
        )
        design = _persist_design(job, design)
        if design.warnings:
            await _emit(job.job_id, "parse", StageStatus.error, "Warning: refinement used assumptions.", {"warnings": design.warnings})
        await _run_downstream(job, design)
    except Exception as exc:  # noqa: BLE001
        await _emit(job.job_id, "pipeline", StageStatus.error, f"Unexpected refinement warning: {exc}", None)
    finally:
        await STORE.finish(job.job_id)


async def _run_downstream(job: JobRecord, design: CircuitDesign) -> None:
    """Stages shared by initial generation and refinement: schematic, PCB, routing, 3D, Gerber."""
    project_name = _slug(design.project_name)
    layout: BoardLayout | None = None

    async def schematic_action() -> dict[str, Any]:
        svg_path = job.output_dir / "schematic.svg"
        kicad_path = job.output_dir / f"{project_name}.kicad_sch"
        svg = write_schematic_svg(design, svg_path)
        write_kicad_schematic(design, kicad_path, project_name=project_name)
        STORE.add_artifact(job.job_id, "schematic_svg", svg_path)
        STORE.add_artifact(job.job_id, "kicad_schematic", kicad_path)
        return {
            "svg": svg,
            "kicad_filename": f"{project_name}.kicad_sch",
            "artifacts": {
                "schematic_svg": f"/api/jobs/{job.job_id}/artifact/schematic_svg",
                "kicad_schematic": f"/api/jobs/{job.job_id}/artifact/kicad_schematic",
            },
        }

    await _safe_stage(
        job,
        "schematic",
        "Rendering schematic SVG and writing KiCad .kicad_sch output.",
        "Schematic SVG and KiCad file generated.",
        schematic_action,
        lambda exc: {"svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"><text x=\"20\" y=\"30\">Schematic fallback</text></svg>", "error": str(exc)},
    )

    async def bom_action() -> dict[str, Any]:
        bom = build_bom(design)
        bom_json_path = job.output_dir / "bom.json"
        bom_csv_path = job.output_dir / f"{project_name}_BOM.csv"
        bom_jlc_path = job.output_dir / f"{project_name}_BOM_JLCPCB.csv"
        bom_json_path.write_text(
            json.dumps(bom.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        write_bom_csv(bom, bom_csv_path)
        write_jlcpcb_csv(bom, bom_jlc_path)
        STORE.add_artifact(job.job_id, "bom_json", bom_json_path)
        STORE.add_artifact(job.job_id, "bom_csv", bom_csv_path)
        STORE.add_artifact(job.job_id, "bom_jlcpcb_csv", bom_jlc_path)
        bom_payload = bom.model_dump(mode="json")
        bom_payload["artifacts"] = {
            "bom_csv": f"/api/jobs/{job.job_id}/artifact/bom_csv",
            "bom_jlcpcb_csv": f"/api/jobs/{job.job_id}/artifact/bom_jlcpcb_csv",
            "bom_json": f"/api/jobs/{job.job_id}/artifact/bom_json",
        }
        bom_payload["filenames"] = {
            "bom_csv": bom_csv_path.name,
            "bom_jlcpcb_csv": bom_jlc_path.name,
        }
        return bom_payload

    await _safe_stage(
        job,
        "bom",
        "Extracting bill of materials and exporting CSV.",
        "BOM ready (engineering + JLCPCB CSV).",
        bom_action,
        lambda exc: {
            "lines": [],
            "total_unique": 0,
            "total_quantity": 0,
            "error": str(exc),
        },
    )

    layout = await _safe_stage(
        job,
        "pcb_layout",
        "Placing components and drawing ratsnest connections.",
        "PCB layout generated.",
        lambda: _async_value(generate_layout(design)),
        lambda exc: generate_layout(fallback_design(job.description, str(exc))),
    )
    layout_path = job.output_dir / "layout.json"
    layout_path.write_text(json.dumps(layout.model_dump(mode="json"), indent=2), encoding="utf-8")
    STORE.add_artifact(job.job_id, "layout_json", layout_path)

    routed = await _safe_stage(
        job,
        "routing",
        "Attempting Lee grid routing with ratsnest fallback.",
        "Routing stage complete.",
        lambda: _async_value(route_layout(layout)),
        lambda exc: layout.model_copy(update={"warnings": [*layout.warnings, str(exc)]}),
    )
    layout = routed
    if layout.warnings:
        await _emit(job.job_id, "routing", StageStatus.error, "Warning: some routes fell back to ratsnest.", {"warnings": layout.warnings})
    layout_path.write_text(json.dumps(layout.model_dump(mode="json"), indent=2), encoding="utf-8")
    pcb_svg_path = job.output_dir / "pcb_layout.svg"
    pcb_svg_path.write_text(layout_svg(layout), encoding="utf-8")
    STORE.add_artifact(job.job_id, "pcb_svg", pcb_svg_path)

    await _safe_stage(
        job,
        "3d",
        "Preparing Three.js board visualization data.",
        "3D board data ready.",
        lambda: _async_value(
            {
                "board": {"width": layout.width, "height": layout.height, "thickness": 1.6},
                "components": [c.model_dump(mode="json") for c in layout.components],
                "traces": [t.model_dump(mode="json") for t in layout.traces],
                "ratsnest": [r.model_dump(mode="json") for r in layout.ratsnest],
            }
        ),
        lambda exc: {"board": {"width": 120, "height": 85, "thickness": 1.6}, "components": [], "traces": [], "ratsnest": [], "error": str(exc)},
    )

    async def gerber_action() -> dict[str, Any]:
        zip_path = write_gerber_zip(layout, job.output_dir, project_name)
        STORE.add_artifact(job.job_id, "gerbers", zip_path)
        return {"download_url": f"/api/jobs/{job.job_id}/artifact/gerbers", "filename": zip_path.name}

    await _safe_stage(
        job,
        "gerber",
        "Exporting demo Gerber package.",
        "Gerber ZIP exported.",
        gerber_action,
        lambda exc: {"error": str(exc), "download_url": None},
    )

    await _emit(
        job.job_id,
        "done",
        StageStatus.complete,
        "Boardsmith pipeline complete.",
        STORE.snapshot(job.job_id),
    )


async def _async_value(value: Any) -> Any:
    return value
