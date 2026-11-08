"""Time Skill Gap runs on the synthetic résumés, one at a time, for one configuration.

Calls prepare → invoke → calculate_web_report directly (the app's run cache would answer
repeats instantly). App code is unchanged. Rounds are interleaved: round 1 runs every
résumé, then round 2, and so on. There are no retries; a failed run is recorded as failed.

    python -m experiments.skill_gap_latency.run --config A --repeats 3
    python -m experiments.skill_gap_latency.run --config A --resume swe_strong --results <local csv>
    python -m experiments.skill_gap_latency.run --dry-run
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.input import prepare
from app.services.skill_gaps.response import calculate_web_report
from app.services.skill_gaps.storage import load, save_json

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
RESULTS = HERE / "results.csv"
RUNS = HERE.parents[1] / "local_results" / "experiments" / "skill_gap_latency"

FAMILIES = {"swe": "software_engineer", "da": "data_analyst", "ai": "ai_engineer"}
LEVELS = ("strong", "medium", "weak")
RESUMES = tuple(f"{role}_{level}" for role in FAMILIES for level in LEVELS)

# One entry per tested setup. B, C and D are added once their Agents exist.
CONFIGS = {
    "A": "Current single Agent, unchanged (gpt-5-mini, medium reasoning, 1 call)",
}

COLUMNS = (
    "config", "resume", "role", "level", "round", "started_at", "status", "error",
    "agent_name", "agent_version", "model", "reasoning_effort", "calls",
    "total_s", "prepare_s", "setup_s", "conversation_s", "inference_s", "scoring_s",
    "input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens",
    "practice", "limited_practice", "knowledge", "absent", "uncertain", "reference_errors",
    "verdicts", "run_dir",
)
VERDICTS = ("practice", "limited_practice", "knowledge", "absent", "uncertain")


class AgentVersionChanged(RuntimeError):
    pass


def schedule(resumes, repeats):
    """Interleaved order: every résumé in round 1, then round 2, ..."""
    return [(name, round_) for round_ in range(1, repeats + 1) for name in resumes]


def default_invoke(config):
    if config != "A":
        raise SystemExit(f"Config {config} is not set up yet.")
    from app.services.skill_gaps.transport import invoke
    return invoke


def usage_fields(raw):
    usage = (raw or {}).get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "cached_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
    }


def verdict_fields(output, report):
    result = (output or {}).get("result") or {}
    verdicts = {skill: [value.get("kind"), value.get("operation_id")]
                for skill, value in result.items() if isinstance(value, dict)}
    counts = {kind: sum(1 for kind_, _ in verdicts.values() if kind_ == kind) for kind in VERDICTS}
    checks = ((report or {}).get("reference_validation") or {})
    errors = len(checks.get("global_errors") or []) + sum(
        len(skill.get("errors") or []) for skill in (checks.get("skills") or {}).values())
    return {**counts, "reference_errors": errors if report else None,
            "verdicts": json.dumps(verdicts, sort_keys=True, separators=(",", ":"))}


def run_one(config, name, round_, *, invoke, catalog, market, runs_root=RUNS, score=calculate_web_report):
    """Run one résumé once. Returns the CSV row; never raises for a failed model call."""
    role, level = name.split("_")
    family = FAMILIES[role]
    started_at = datetime.now(timezone.utc)
    folder = runs_root / config / f"{started_at:%Y%m%dT%H%M%SZ}_{name}_r{round_}"
    saved = {}

    def save(file_name, value):
        saved[file_name] = value
        save_json(folder / file_name, value)

    row = {"config": config, "resume": name, "role": family, "level": level, "round": round_,
           "started_at": started_at.isoformat(timespec="seconds"), "status": "ok", "error": "",
           "calls": 0, "run_dir": f"{config}/{folder.name}"}
    timings, output, report = {}, None, None
    started = time.perf_counter()
    try:
        step = time.perf_counter()
        payload = prepare(family, load(FIXTURES / f"{name}.json"), name, catalog)
        row["prepare_s"] = round(time.perf_counter() - step, 3)
        save("input.json", payload)

        def on_request():
            row["calls"] += 1

        output = invoke(payload, save, on_request, timings)
        save("agent.response.json", output)
        step = time.perf_counter()
        report = score(family, output, catalog, market, payload["resume_sources"])
        row["scoring_s"] = round(time.perf_counter() - step, 3)
        save("skill_gaps.json", report)
    except Exception as error:  # recorded, not retried
        row.update(status="failed", error=f"{type(error).__name__}: {error}"[:300])
    row["total_s"] = round(time.perf_counter() - started, 3)

    agent = saved.get("observed_agent.json") or {}
    definition = agent.get("definition") or {}
    raw = saved.get("agent.raw.json")
    row.update(
        agent_name=agent.get("name"), agent_version=agent.get("version"),
        model=(raw or {}).get("model") or definition.get("model"),
        reasoning_effort=((raw or {}).get("reasoning") or definition.get("reasoning") or {}).get("effort"),
        setup_s=timings.get("sdk_auth_configuration_seconds"),
        conversation_s=_sum(timings.get("conversation_create_seconds"), timings.get("conversation_delete_seconds")),
        inference_s=timings.get("inference_seconds"),
        **usage_fields(raw), **verdict_fields(output, report),
    )
    save("metrics.json", {**row, "timings": timings, "verdicts": json.loads(row["verdicts"])})
    return row


def _sum(*values):
    present = [value for value in values if value is not None]
    return round(sum(present), 3) if present else None


def append_row(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerow(row)


def run(config, resumes, repeats, *, invoke, results=RESULTS, runs_root=RUNS, max_calls=None,
        score=calculate_web_report, log=print):
    catalog = load(ASSET_ROOT / "core_catalog.json")
    market = load(ASSET_ROOT / "market_snapshot.json")
    plan = schedule(resumes, repeats)
    if max_calls is not None:
        plan = plan[:max_calls]
    version, rows = None, []
    for index, (name, round_) in enumerate(plan, 1):
        row = run_one(config, name, round_, invoke=invoke, catalog=catalog, market=market,
                      runs_root=runs_root, score=score)
        append_row(results, row)
        rows.append(row)
        log(f"[{index}/{len(plan)}] {config} {name} r{round_}: {row['status']} "
            f"total={row['total_s']}s inference={row.get('inference_s')}s "
            f"out={row.get('output_tokens')} v{row.get('agent_version')}")
        if row.get("agent_version"):
            if version is None:
                version = row["agent_version"]
            elif row["agent_version"] != version:
                raise AgentVersionChanged(
                    f"Agent version changed from {version} to {row['agent_version']}; runs are no longer comparable.")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="A", choices=sorted(CONFIGS))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--resume", action="append", choices=RESUMES, help="Repeatable. Default: all 9.")
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--results", type=Path, default=RESULTS, help="CSV to append to.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare inputs only; no model calls.")
    args = parser.parse_args(argv)
    resumes = tuple(args.resume or RESUMES)

    if args.dry_run:
        catalog = load(ASSET_ROOT / "core_catalog.json")
        for name in resumes:
            payload = prepare(FAMILIES[name.split("_")[0]], load(FIXTURES / f"{name}.json"), name, catalog)
            print(f"{name:11} skills={len(payload['core_skills'])} chars={len(json.dumps(payload))}")
        print(f"{len(schedule(resumes, args.repeats))} runs planned; nothing was sent.")
        return 0

    try:
        rows = run(args.config, resumes, args.repeats, invoke=default_invoke(args.config),
                   results=args.results, max_calls=args.max_calls)
    except AgentVersionChanged as error:
        print(error, file=sys.stderr)
        return 2
    failed = sum(row["status"] != "ok" for row in rows)
    print(f"Done: {len(rows)} runs, {failed} failed. Rows appended to {args.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
