"""Manual live smoke test; sends synthetic fixtures through the configured Foundry Agent."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.deps import get_current_db_user
from app.main import app
from app.models import User


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("resumes", nargs="+", type=Path)
    args = parser.parse_args()
    # Tests the résumé pipeline, not login: skip the token check.
    app.dependency_overrides[get_current_db_user] = lambda: User(email="smoke@example.com")
    client = TestClient(app)
    failed = False

    for path in args.resumes:
        with path.open("rb") as handle:
            response = client.post(
                "/resumes/analyze",
                files={"file": (path.name, handle, "application/octet-stream")},
            )
        if response.status_code != 200:
            failed = True
            print(path.name, response.status_code, response.json().get("detail"))
            continue
        body = response.json()
        extraction = body["extraction"]
        agent = body["agent"]
        print(
            path.name,
            response.status_code,
            extraction["parser"],
            f"{extraction['characters']} chars",
            f"OCR pages={extraction['ocr_pages']}",
            f"Agent={agent['seconds']:.4f}s",
            f"categories={len(body['classification'])}",
        )
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
