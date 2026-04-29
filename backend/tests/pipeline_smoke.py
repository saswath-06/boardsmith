from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import STORE
from app.pipeline import run_pipeline


async def main() -> None:
    job = STORE.create(
        "An ESP32 microcontroller connected to a DHT22 temperature sensor, "
        "an LED indicator with a current limiting resistor, and USB-C power."
    )
    await run_pipeline(job)
    snapshot = STORE.snapshot(job.job_id)
    assert snapshot is not None
    assert snapshot.complete
    stages = [event.stage for event in snapshot.events]
    for stage in ("parse", "schematic", "pcb_layout", "routing", "3d", "gerber", "done"):
        assert stage in stages, f"missing stage {stage}"
    artifact_names = {artifact.name for artifact in snapshot.artifacts}
    for artifact in ("circuit_json", "schematic_svg", "kicad_schematic", "layout_json", "pcb_svg", "gerbers"):
        assert artifact in artifact_names, f"missing artifact {artifact}"
    print(job.job_id)
    print("events", len(snapshot.events))
    print("artifacts", sorted(artifact_names))


if __name__ == "__main__":
    asyncio.run(main())
