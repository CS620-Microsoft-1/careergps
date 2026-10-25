"""One selected family, one evidence call, local integrity check and fixed scoring."""
import argparse
import json
import os
from pathlib import Path
import time

from .policy import calculate, POLICY_VERSION
from .schema import SCHEMA_NAME
from .sources import build_sources

ROOT = Path(__file__).parent


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def prepare(family, resume, resume_id, catalog):
    return {
        "task": "extract_resume_evidence", "job_family": family, "resume_id": resume_id, "evidence_contract": SCHEMA_NAME,
        "resume_sources": build_sources(resume),
        "core_skills": [{**skill, "module_id": module["module_id"]}
                        for module in catalog["families"][family]["modules"]
                        for skill in module["skills"]],
    }


def load_paired_response(path, payload):
    """Unit IDs are snapshot-local: offline replay needs its original input."""
    original_input = Path(path).with_name("input.json")
    if not original_input.exists():
        raise ValueError("Saved output replay requires its original adjacent input.json")
    if load(original_input) != payload:
        raise ValueError("Saved output belongs to another input snapshot; IDs cannot be reused")
    return load(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True,
                        choices=["software_engineer", "data_analyst", "ai_engineer"])
    parser.add_argument("--resume", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--agent-output", type=Path, help="Check and score a saved v12 response offline")
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Use a new empty output directory to preserve previous runs")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    catalog, market = load(ROOT / "core_catalog.json"), load(ROOT / "market_snapshot.json")
    payload = prepare(args.family, load(args.resume), args.resume.stem, catalog)
    save = lambda name, value: save_json(args.output_dir / name, value)
    save("input.json", payload)
    metadata = {"mode": "prepare_only" if args.prepare_only else
                "offline_existing_response" if args.agent_output else "saved_agent_bound",
                "database_used": False, "reference_integrity_check": True,
                "semantic_evidence_validation": False, "exact_quote_integrity_check": True, "repair_calls": 0,
                "summary_calls": 0, "model_calls": 0,
                "reference_check_status": "not_run_no_agent_response",
                "core_skill_count": len(payload["core_skills"]), "job_family": args.family,
                "policy_version": POLICY_VERSION, "expected_schema_name": SCHEMA_NAME,
                "resume_activity_count": len(payload["resume_sources"]),
                "resume_unit_count": sum(len(source["units"]) for source in payload["resume_sources"]),
                "max_selected_activity_per_core": 1}
    metadata["input_preparation_seconds"] = round(time.perf_counter() - start, 6)
    save("run.json", metadata)
    if not args.prepare_only:
        try:
            if args.agent_output:
                output = load_paired_response(args.agent_output, payload)
                metadata["existing_response_source"] = str(args.agent_output.resolve())
            else:
                from .transport import invoke
                agent_start = time.perf_counter()
                metadata["azure_phase_timings"] = {}
                def on_request():
                    metadata["model_calls"] += 1
                    save("run.json", metadata)
                output = invoke(payload, save, on_request, metadata["azure_phase_timings"])
                metadata["agent_seconds"] = round(time.perf_counter() - agent_start, 3)
            save("agent.response.json", output)
            compute_start = time.perf_counter()
            report = calculate(args.family, output, catalog, market, payload["resume_sources"])
            report["resume_id"] = args.resume.stem
            save("local_checks.json", report["reference_validation"])
            save("coverage_audit.json", report["evidence_coverage"])
            save("skill_gaps.json", report)
            metadata["reference_check_status"] = report["reference_validation"]["status"]
            metadata["unscored_skill_count"] = len(report["unscored_skill_ids"])
            metadata["python_seconds"] = round(time.perf_counter() - compute_start, 6)
        except Exception as error:
            metadata.update(status="failed", error_type=type(error).__name__,
                            elapsed_seconds=round(time.perf_counter() - start, 3))
            save("run.json", metadata)
            raise
    metadata.update(status="prepared" if args.prepare_only else "completed",
                    elapsed_seconds=round(time.perf_counter() - start, 3))
    save("run.json", metadata)
    print(json.dumps({**metadata, "output_dir": str(args.output_dir.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
