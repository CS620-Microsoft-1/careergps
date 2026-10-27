"""Replay the frozen qualification rules or export an existing demand aggregate.

This offline tool never connects to a database, calls a model, or overwrites the
runtime snapshot. Input files and output destinations are always explicit.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from scripts.demand_rules.compact import Engine, aggregate_compact, posting
from scripts.demand_rules.fine import LEVELS
from scripts.demand_rules.taxonomy import CATALOG, VERSION

COUNT_FIELDS = (
    "required_job_count", "preferred_only_job_count", "unspecified_job_count",
    "required_ratio", "preferred_only_ratio", "unspecified_ratio",
)
RULE_ROOT = Path(__file__).with_name("demand_rules")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def read_source(*, source_zip: Path | None = None,
                parents_path: Path | None = None, qualifications_path: Path | None = None):
    """Read the two relevant tables without extracting a ZIP to the filesystem."""
    if source_zip is not None:
        if parents_path is not None or qualifications_path is not None:
            raise ValueError("Choose the ZIP or the two JSON files, not both.")
        with ZipFile(source_zip) as archive:
            tables = {}
            for filename in ("job_postings_analyses.json", "job_analysis_qualifications.json"):
                matches = [name for name in archive.namelist()
                           if not name.startswith("__MACOSX/") and Path(name).name == filename]
                if len(matches) != 1:
                    raise ValueError(f"The ZIP must contain exactly one {filename}.")
                tables[filename] = json.loads(archive.read(matches[0]).decode("utf-8-sig"))
        return (tables["job_postings_analyses.json"], tables["job_analysis_qualifications.json"],
                {"source_kind": "six_table_zip", "source_sha256": digest(source_zip)})
    if parents_path is None or qualifications_path is None:
        raise ValueError("Provide --source-zip or both --postings and --qualifications.")
    return (load(parents_path), load(qualifications_path), {
        "source_kind": "two_table_json", "postings_sha256": digest(parents_path),
        "qualifications_sha256": digest(qualifications_path),
    })


def validate_source(parents, qualifications):
    if not isinstance(parents, list) or not isinstance(qualifications, list):
        raise ValueError("Each source table must be a JSON array.")
    parent = {}
    for row in parents:
        pid = row.get("job_posting_id")
        if not isinstance(pid, str) or not pid or pid in parent:
            raise ValueError("Parent posting IDs must be unique nonempty strings.")
        if row.get("job_family") not in (*CATALOG, None):
            raise ValueError(f"Unknown job family for posting {pid}.")
        parent[pid] = row
    by_job = defaultdict(list)
    for index, row in enumerate(qualifications):
        pid = row.get("job_posting_id")
        if pid not in parent or row.get("level") not in LEVELS:
            raise ValueError(f"Invalid posting reference or qualification level at row {index}.")
        if not isinstance(row.get("value"), str) or not isinstance(row.get("position"), int):
            raise ValueError(f"Qualification row {index} needs text and an integer position.")
        if not isinstance(row.get("categories", []), list):
            raise ValueError(f"Qualification categories must be an array at row {index}.")
        if "evidence" not in row:
            raise ValueError(f"Qualification row {index} is missing evidence.")
        by_job[pid].append((index, row))
    return parent, by_job


def replay(parents, qualifications, *, source: dict | None = None,
           output: Path | None = None, batch_size: int = 100) -> dict:
    """Count each posting once per core, with required > preferred > unspecified."""
    if batch_size < 1:
        raise ValueError("Batch size must be positive.")
    parent, by_job = validate_source(parents, qualifications)
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
    engine = Engine(load(RULE_ROOT / "base_catalog.json"))
    rules = {path.name: digest(path) for path in sorted(RULE_ROOT.iterdir())
             if path.suffix in (".py", ".json")}
    source = source or {"source_kind": "in_memory", "input_sha256": canonical_digest([parents, qualifications])}
    fingerprint = canonical_digest({"analysis_version": VERSION, "rules": rules, "source": source})
    families = []
    review_count = 0
    for family in CATALOG:
        ids = sorted(pid for pid, row in parent.items() if row.get("job_family") == family)
        posts = []
        for start in range(0, len(ids), batch_size):
            batch_ids = ids[start:start + batch_size]
            batch = [posting(engine, family, pid, by_job.get(pid, [])) for pid in batch_ids]
            review_count += sum(len(row["review_items"]) for row in batch)
            if output is not None:
                save_new(output / family / "batches" / f"batch_{start // batch_size + 1:04d}.json", {
                    "fingerprint": fingerprint, "posting_ids": batch_ids, "postings": batch,
                })
            # Retain only aggregation fields in memory; detailed source references
            # have already been checkpointed when an output directory was given.
            posts.extend({key: row[key] for key in (
                "job_posting_id", "qualification_count", "core_requirements", "module_requirements",
                "professional_requirements", "core_conditional_requirements",
                "module_conditional_requirements", "professional_conditional_requirements",
            )} for row in batch)
        result = aggregate_compact(family, posts)
        families.append(result)
        if output is not None:
            save_new(output / family / "demand_ratio.json", result)
    analysis = {
        "analysis_version": VERSION, "schema_version": "3.0", "fingerprint": fingerprint,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "computed_with_review_queue", "source": source, "rule_sha256": rules,
        "counting_semantics": {
            "unit": "Unique job_posting_id within its supplied job_family.",
            "levels": "Posting-level required > preferred > unspecified; review is not unspecified.",
            "denominator": "All supplied parent postings in the family, including no-qualification postings.",
            "scope": "All seniorities in the supplied export; no date or geography filter is inferred.",
        },
        "quality": {
            "source_parent_postings": len(parents), "source_qualification_rows": len(qualifications),
            "scoped_postings": sum(row["total_job_count"] for row in families),
            "excluded_null_family_postings": sum(row.get("job_family") is None for row in parents),
            "review_items": review_count,
        },
        "job_families": families,
    }
    if output is not None:
        save_new(output / "demand_analysis.json", analysis)
    return analysis


def snapshot_from_analysis(analysis: dict, *, source_sha256: str) -> dict:
    """Export the original six count/ratio fields without recounting postings."""
    snapshot = {
        "source_analysis_version": analysis["analysis_version"],
        "source_fingerprint": analysis["fingerprint"],
        "source_status": analysis.get("status"), "source_sha256": source_sha256,
        "counts_recomputed": False, "families": {},
    }
    families = analysis["job_families"]
    if len(families) != len(CATALOG) or {row["job_family"] for row in families} != set(CATALOG):
        raise ValueError("The aggregate must contain exactly the three supported job families.")
    for row in families:
        family = row["job_family"]
        expected = {skill["skill_id"] for module in CATALOG[family] for skill in module["skills"]}
        if len(row["skills"]) != len(expected) or {skill["skill_id"] for skill in row["skills"]} != expected:
            raise ValueError(f"Core skill IDs do not match the fixed catalog for {family}.")
        snapshot["families"][family] = {
            "total_job_count": row["total_job_count"],
            "skills": {skill["skill_id"]: {key: skill[key] for key in COUNT_FIELDS} for skill in row["skills"]},
        }
    return snapshot


def verify_counts(analysis: dict, reference: dict) -> None:
    computed = snapshot_from_analysis(analysis, source_sha256="not-compared")
    if computed["families"] != reference["families"]:
        raise ValueError("Replayed posting counts or demand ratios differ from the reference snapshot.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    replay_parser = commands.add_parser("replay", help="Recompute from the two exported tables using frozen rules.")
    replay_parser.add_argument("--source-zip", type=Path)
    replay_parser.add_argument("--postings", type=Path)
    replay_parser.add_argument("--qualifications", type=Path)
    replay_parser.add_argument("--output", type=Path, required=True, help="A new output directory.")
    replay_parser.add_argument("--batch-size", type=int, default=100)
    replay_parser.add_argument("--verify-snapshot", type=Path)
    export_parser = commands.add_parser("export", help="Export an existing aggregate without changing its numbers.")
    export_parser.add_argument("--analysis", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True, help="A new JSON file.")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            snapshot = snapshot_from_analysis(load(args.analysis), source_sha256=digest(args.analysis))
            save_new(args.output, snapshot)
            print(json.dumps({"status": "exported", "counts_recomputed": False}))
        else:
            parents, qualifications, source = read_source(source_zip=args.source_zip,
                parents_path=args.postings, qualifications_path=args.qualifications)
            analysis = replay(parents, qualifications, source=source, output=args.output, batch_size=args.batch_size)
            if args.verify_snapshot:
                verify_counts(analysis, load(args.verify_snapshot))
            print(json.dumps({"status": "verified" if args.verify_snapshot else "replayed",
                              "sample_sizes": {row["job_family"]: row["total_job_count"] for row in analysis["job_families"]}}))
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
