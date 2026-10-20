"""Fresh API-enforced final-stage replay; preserves all earlier failure artifacts."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import BACKEND_ROOT, SkillGapSettings
from app.services.skill_gap_agent import SkillGapAgentError, call_foundry, response_format
from scripts.test_skill_gap_structured_local import (
    FinalOutput, INVOCATION, validate_final, write_json,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-audit", type=Path, default=BACKEND_ROOT / "local_results" / "skill_gap" / "structured_20_20261020_audit")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = args.output_dir or args.source_audit.parent / f"api_schema_replay_{stamp}"
    root.mkdir(parents=True, exist_ok=False)
    calculated = json.loads((args.source_audit / "03_systems_research_calculated.json").read_text(encoding="utf-8"))
    request = {"task": "explain_skill_gaps", "mode": "market_analysis", "data_source": "synthetic",
               "input": calculated, "output_schema": FinalOutput.model_json_schema()}
    write_json(root / "request.json", request)
    write_json(root / "api_text_format.json", response_format(request["output_schema"], request["task"]))
    (root / "invocation_contract.txt").write_text(INVOCATION, encoding="utf-8")
    metadata = {"started_at": datetime.now(timezone.utc).isoformat(), "database_used": False,
                "cached_response_used": False, "stage": "explain_skill_gaps", "case": "03_systems_research"}
    response_metadata = {}
    try:
        print("Calling existing Azure Agent with API-level strict JSON Schema...", flush=True)
        raw = call_foundry(request, INVOCATION, SkillGapSettings(), max_output_tokens=12000,
                           output_schema=request["output_schema"], schema_name=request["task"],
                           response_metadata=response_metadata)
        (root / "agent_response_raw.json").write_text(raw, encoding="utf-8")
        result = FinalOutput.model_validate_json(raw)
        validate_final(result, calculated)
        write_json(root / "result.json", result.model_dump())
        metadata["status"] = "passed"
        report = ["API-level strict JSON Schema replay", "", "Case: Casey / systems research",
                  "Status: passed", "Fresh final-stage call; earlier extraction/calculation inputs reused unchanged.",
                  "No database, cloud Agent edit, Git commit/push or PR.", "", result.summary, ""]
        report.extend(f"{c.name}: evidence={c.resume_match.evidence_score}; gap={c.gap.score}" for c in result.criteria)
        report.extend(["", "Format validation does not prove factual accuracy or completeness. Earlier evidence-coverage limitations remain."])
        (root / "results.txt").write_text("\n".join(report), encoding="utf-8")
        print("PASS: JSON schema and all immutable numeric/source fields validated.", flush=True)
    except (ValueError, SkillGapAgentError) as error:
        metadata.update(status="failed", error=str(error))
        (root / "results.txt").write_text("Status: failed\n" + str(error), encoding="utf-8")
        print(f"FAILED: {error}", flush=True)
    finally:
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(root / "response_metadata.json", response_metadata)
        write_json(root / "run.json", metadata)
        print(f"Local result: {root}", flush=True)
    return 0 if metadata["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
