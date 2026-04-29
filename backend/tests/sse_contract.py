from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    with TestClient(app) as client:
        create = client.post(
            "/api/jobs",
            json={"description": "ESP32, DHT22, LED indicator, USB-C input, and AMS1117 regulator"},
        )
        create.raise_for_status()
        job_id = create.json()["job_id"]
        seen = []
        with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                assert set(payload) == {"stage", "status", "data", "message"}
                assert payload["status"] in {"running", "complete", "error"}
                seen.append(payload["stage"])
                if payload["stage"] == "done":
                    break
        assert "parse" in seen
        assert "gerber" in seen
        assert "done" in seen
        print(job_id)
        print("sse events", len(seen))


if __name__ == "__main__":
    main()
