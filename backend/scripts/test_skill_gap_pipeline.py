"""Raw Review JSON + job descriptions -> Agent extraction -> Python scores -> local report."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import BACKEND_ROOT, SkillGapSettings
from app.schemas.skill_gap import SkillGapResult
from app.schemas.skill_gap_extraction import (
    JobRequirementsExtraction, PostingSnapshot, ResumeEvidenceExtraction, ReviewedResume, TargetScope,
)
from app.services.skill_gap import calculate_gaps, normalize_skill, validate_agent_result
from app.services.skill_gap_agent import SkillGapAgentError, call_foundry
from app.services.skill_gap_extraction import aggregate_market, score_resume, select_postings
from scripts.test_skill_gap_local import FIXTURES, PROMPT, render_report, save_json


def run(args: argparse.Namespace, agent_call=None, *, agent_mode: str | None = None) -> tuple[Path, bool]:
    injected = agent_call is not None
    agent_call = agent_call or call_foundry
    started = datetime.now(timezone.utc)
    folder = args.output_dir.resolve() / f"{started:%Y%m%dT%H%M%SZ}_pipeline_{uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    metadata = {"status": "started", "database_used": False,
                "mode": agent_mode or ("injected-test-agent" if injected else "live"),
                "started_at": started.isoformat(), "pipeline_version": "raw-input-v2"}
    stage = "input_validation"
    try:
        reviewed = ReviewedResume.model_validate_json(args.resume.read_text(encoding="utf-8-sig"))
        snapshot = PostingSnapshot.model_validate_json(args.postings.read_text(encoding="utf-8-sig"))
        scope = TargetScope.model_validate_json(args.scope.read_text(encoding="utf-8-sig"))
        metadata["data_source"] = snapshot.data_source
        save_json(folder / "reviewed_resume.json", reviewed.model_dump(mode="json"))
        save_json(folder / "job_descriptions.json", snapshot.model_dump(mode="json"))
        save_json(folder / "target_scope.json", scope.model_dump(mode="json"))
        selected, filtering = select_postings(snapshot, scope)
        save_json(folder / "posting_filter_audit.json", {"records": filtering})
        prompt = PROMPT.read_text(encoding="utf-8")
        (folder / "prompt.md").write_text(prompt, encoding="utf-8")
        metadata["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
        metadata["raw_postings"] = len(snapshot.postings)
        metadata["selected_postings"] = len(selected)
        settings = SkillGapSettings()
        metadata["agent_name"] = settings.skill_gap_foundry_agent_name

        def ask(task: str, payload: dict, model):
            request = {"task": task, "data_source": snapshot.data_source, "input": payload,
                       "output_schema": model.model_json_schema()}
            save_json(folder / f"{task}_request.json", request)
            print(f"Running {task}...", flush=True)
            raw = agent_call(request, prompt, settings)
            (folder / f"{task}_raw.txt").write_text(raw, encoding="utf-8")
            result = model.model_validate_json(raw)
            save_json(folder / f"{task}_extraction.json", result.model_dump())
            return result

        stage = "extract_job_requirements"
        job_extraction = ask(stage, {"postings": [
            {"posting_id": d.posting_id, "company_name": d.company_name,
             "posting": d.posting.model_dump(mode="json")} for d in selected
        ]}, JobRequirementsExtraction)
        market, market_audit = aggregate_market(job_extraction, selected, scope)
        save_json(folder / "market_profile.json", market.model_dump())
        save_json(folder / "market_skill_counts.json", {"skills": market_audit})

        stage = "extract_resume_evidence"
        # Match market requirements plus explicitly declared candidate skills. No contact data is sent.
        wanted = {}
        for skill in [item.skill for item in market.skills] + reviewed.classification.technical_skills:
            name = normalize_skill(skill)
            wanted.setdefault(name.casefold(), name)
        skills = sorted(wanted.values(), key=str.casefold)
        resume_extraction = ask(stage, {
            "reviewed_resume": reviewed.classification.model_dump(exclude={"personal_information"}),
            "skills_to_check": skills,
        }, ResumeEvidenceExtraction)
        scored, resume_audit = score_resume(resume_extraction, reviewed, skills)
        save_json(folder / "confirmed_resume.json", scored.model_dump())
        save_json(folder / "resume_evidence_audit.json", {"skills": resume_audit})

        stage = "explain_skill_gaps"
        inputs = calculate_gaps(scored, market)
        save_json(folder / "agent_input.json", inputs.model_dump())
        ask(stage, inputs.model_dump(), SkillGapResult)
        raw = (folder / f"{stage}_raw.txt").read_text(encoding="utf-8")
        result = validate_agent_result(raw, inputs)
        result.limitations.extend([
            "Demand counts include required and preferred mentions, counted once per posting; "
            "context and explicitly negated mentions are excluded.",
            "This is résumé evidence coverage, not verified skill proficiency or hiring probability. "
            "Quote validation checks grounding, not the correctness of every Agent category.",
        ])
        if snapshot.data_source == "synthetic":
            result.limitations.append("All input documents are synthetic; computed frequencies are not real market statistics.")
        save_json(folder / "result.json", result.model_dump())
        report = render_report(result, metadata["mode"], snapshot.data_source)
        report += "\n## Computation audit\n\n"
        report += (f"Selected {len(selected)} of {len(snapshot.postings)} input records; "
                   f"{market.company_count} companies. Publication window ending {scope.as_of}.\n\n")
        report += "| Skill | Required | Preferred only | Denominator | Frequency |\n|---|---:|---:|---:|---:|\n"
        for item in market_audit:
            name = item["skill"].replace("|", "\\|")
            report += (f"| {name} | {item['required_postings']} | {item['preferred_only_postings']} "
                       f"| {item['denominator']} | {item['frequency']:.1%} |\n")
        report += "\nSee resume_evidence_audit.json and market_skill_counts.json for exact source quotations.\n"
        (folder / "report.md").write_text(report, encoding="utf-8")
        metadata["status"] = "passed"
    except (ValueError, OSError, SkillGapAgentError) as error:
        if isinstance(error, ValidationError):
            reason = "Input/Agent schema validation failed; inspect the saved request and raw reply."
        elif isinstance(error, OSError):
            reason = f"Local file operation failed ({type(error).__name__})."
        else:
            reason = str(error)
        metadata.update(status="failed", failed_stage=stage, error=reason)
        save_json(folder / "error.json", {"stage": stage, "error": reason})
        print(f"FAILED at {stage}: {reason}", flush=True)
    finally:
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        metadata["seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 3)
        save_json(folder / "run.json", metadata)
    print(f"Local artifacts: {folder}", flush=True)
    return folder, metadata["status"] == "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute from raw JSON content; real Agent calls, no database.")
    parser.add_argument("--resume", type=Path, default=FIXTURES / "reviewed_resume.json")
    parser.add_argument("--postings", type=Path, default=FIXTURES / "job_descriptions.json")
    parser.add_argument("--scope", type=Path, default=FIXTURES / "target_scope.json")
    parser.add_argument("--output-dir", type=Path, default=BACKEND_ROOT / "local_results" / "skill_gap")
    _, success = run(parser.parse_args())
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
