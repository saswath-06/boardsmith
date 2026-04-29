from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app

PROMPT = (
    "An ESP32 microcontroller connected to a DHT22 temperature sensor, an LED indicator "
    "with a current limiting resistor, and a USB-C power input with an AMS1117 3.3V "
    "regulator and decoupling capacitors."
)


def main() -> None:
    with TestClient(app) as client:
        created = client.post("/api/jobs", json={"description": PROMPT})
        created.raise_for_status()
        job_id = created.json()["job_id"]
        with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                if payload["stage"] == "done":
                    break

        snapshot = client.get(f"/api/jobs/{job_id}")
        snapshot.raise_for_status()
        artifact_names = {artifact["name"] for artifact in snapshot.json()["artifacts"]}
        required = {"circuit_json", "schematic_svg", "kicad_schematic", "layout_json", "pcb_svg", "gerbers"}
        missing = required - artifact_names
        assert not missing, f"missing artifacts: {sorted(missing)}"

        schematic = client.get(f"/api/jobs/{job_id}/artifact/schematic_svg")
        assert schematic.status_code == 200 and "<svg" in schematic.text
        kicad = client.get(f"/api/jobs/{job_id}/artifact/kicad_schematic")
        assert kicad.status_code == 200 and "(kicad_sch" in kicad.text
        gerbers = client.get(f"/api/jobs/{job_id}/artifact/gerbers")
        assert gerbers.status_code == 200 and len(gerbers.content) > 100

        print(job_id)
        print("artifacts", sorted(artifact_names))
        print("gerber_bytes", len(gerbers.content))


if __name__ == "__main__":
    main()
