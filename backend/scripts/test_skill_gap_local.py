"""Run from backend: python -m scripts.test_skill_gap_local --mode mock|live."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import BACKEND_ROOT, SkillGapSettings
from app.schemas.skill_gap import ConfirmedResume, MarketInput, SkillGapResult
from app.services.skill_gap import calculate_gaps, mock_response, validate_agent_result
from app.services.skill_gap_agent import SkillGapAgentError, call_foundry

FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "skill_gap"
PROMPT = BACKEND_ROOT.parent / "docs" / "skill-gap-agent-prompt.md"


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_report(result: SkillGapResult, mode: str, data_source: str = "synthetic") -> str:
    lines = [
        "# Local Skill Gap test result", "",
        f"Mode: {mode}. Data source: {data_source}; no database used.", "",
        f"Target: {result.target_role} / {result.seniority}", "",
        f"Sample confidence: {result.confidence} (not a verification of market accuracy)", "",
        result.summary, "",
    ]
    for gap in result.gaps:
        lines.extend([
            f"## {gap.skill} ({gap.priority})", "",
            f"Market frequency: {gap.market_frequency:.1%}; "
            f"evidence score: {gap.user_evidence_score}; gap score: {gap.gap_score}", "",
            gap.reason, "", f"Action: {gap.recommended_action}", "",
            f"Completion evidence: {gap.completion_evidence}", "",
        ])
    if result.strengths:
        lines.extend(["## Strengths", ""])
        lines.extend(f"- {item.skill}: {item.explanation}" for item in result.strengths)
        lines.append("")
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> tuple[Path, bool]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.output_dir.resolve() / f"{stamp}_{args.mode}_{uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc)
    metadata = {
        "mode": args.mode, "status": "started", "database_used": False,
        "data_source": "local JSON files (default fixtures are synthetic)",
        "scoring_version": "frequency-times-evidence-gap-v1",
        "started_at": started.isoformat(),
    }
    save_json(folder / "run.json", metadata)
    try:
        resume = ConfirmedResume.model_validate_json(args.resume.read_text(encoding="utf-8-sig"))
        market = MarketInput.model_validate_json(args.market.read_text(encoding="utf-8-sig"))
        save_json(folder / "confirmed_resume.json", resume.model_dump())
        save_json(folder / "market_profile.json", market.model_dump())
        inputs = calculate_gaps(resume, market)
        save_json(folder / "agent_input.json", inputs.model_dump())
        prompt = PROMPT.read_text(encoding="utf-8")
        (folder / "prompt.md").write_text(prompt, encoding="utf-8")
        metadata["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if args.mode == "live":
            settings = SkillGapSettings()
            metadata["agent_name"] = settings.skill_gap_foundry_agent_name
            raw = call_foundry(inputs, prompt, settings)
        else:
            raw = mock_response(inputs)
        (folder / "raw_response.txt").write_text(raw, encoding="utf-8")
        result = validate_agent_result(raw, inputs)
        save_json(folder / "result.json", result.model_dump())
        (folder / "report.md").write_text(render_report(result, args.mode), encoding="utf-8")
        metadata["status"] = "passed"
    except (ValueError, OSError, SkillGapAgentError) as error:
        # Pydantic's full error text can include raw input values; never print it.
        if isinstance(error, ValidationError):
            reason = "Input or Agent output failed the JSON schema. Inspect the local input/raw response files."
        elif isinstance(error, SkillGapAgentError):
            reason = str(error)
        elif isinstance(error, OSError):
            reason = f"Local file operation failed ({type(error).__name__})."
        else:
            reason = str(error)
        metadata.update(status="failed", error_type=type(error).__name__, error=reason)
        save_json(folder / "error.json", {"error_type": type(error).__name__, "message": reason})
        print(f"FAILED: {reason}")
    finally:
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        metadata["seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 3)
        save_json(folder / "run.json", metadata)
    print(f"Local artifacts: {folder}")
    return folder, metadata["status"] == "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description="File-based Skill Gap experiment; no DB initialization.")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--resume", type=Path, default=FIXTURES / "confirmed_resume.json")
    parser.add_argument("--market", type=Path, default=FIXTURES / "market_profile.json")
    parser.add_argument("--output-dir", type=Path, default=BACKEND_ROOT / "local_results" / "skill_gap")
    args = parser.parse_args()
    _, passed = run(args)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
