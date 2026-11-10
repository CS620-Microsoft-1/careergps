"""Pull real projects from the GitHub sources in data/project_sources.yaml into data/github_projects.json.

Run from backend/ (weekly is plenty; the resources agent reads the saved file, never GitHub live):
    python -m scripts.sync_github_projects
    python -m scripts.sync_github_projects --source cool_coders
    python -m scripts.sync_github_projects --dry-run

Set GITHUB_TOKEN (a fine-grained token with no permissions is enough) to raise the search API
limit from 10 to 30 requests a minute. A source that fails keeps its entries from the last run,
so one GitHub hiccup does not empty the catalog. Exits 1 only when every source failed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.github_projects import build_catalog, create_client, fetch_idea_list, fetch_topic  # noqa: E402

SOURCES_PATH = BACKEND_ROOT / "data" / "project_sources.yaml"
OUTPUT_PATH = BACKEND_ROOT / "data" / "github_projects.json"
FETCHERS = {"idea_list": fetch_idea_list, "topic": fetch_topic}


def _source_of(entry_id: str, source_ids: list[str]) -> str | None:
    # ids look like gh_<family>_<source_id>_<slug>
    rest = entry_id.split("_", 2)[-1] if entry_id.startswith("gh_") else ""
    return next((source for source in source_ids if rest.startswith(source + "_")), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", action="append", default=[], help="source id from project_sources.yaml")
    parser.add_argument("--dry-run", action="store_true", help="print counts without writing the file")
    args = parser.parse_args()

    sources = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))["sources"]
    if args.source:
        sources = [source for source in sources if source["id"] in args.source]
    all_ids = [source["id"] for source in yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))["sources"]]

    previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")) if OUTPUT_PATH.exists() else []
    kept = {entry["id"]: entry for entry in previous}
    failures = 0
    with create_client(os.environ.get("GITHUB_TOKEN")) as client:
        for source in sources:
            try:
                raw = FETCHERS[source["kind"]](client, source)
            except Exception as error:  # keep last run's entries for this source
                failures += 1
                print(f"error {source['id']}: {type(error).__name__}: {error}")
                continue
            entries = build_catalog(raw)
            kept = {k: v for k, v in kept.items() if _source_of(k, all_ids) != source["id"]}
            kept.update({entry["id"]: entry for entry in entries})
            print(f"ok    {source['id']}: {len(raw)} projects -> {len(entries)} role entries")

    # A repo can carry several of the configured topics; offer it once per role (first source wins).
    order = {source_id: index for index, source_id in enumerate(all_ids)}
    unique: dict[tuple[str, str], dict] = {}
    for entry in sorted(kept.values(), key=lambda e: (order.get(_source_of(e["id"], all_ids), len(order)), e["id"])):
        unique.setdefault((entry["career_path"], entry.get("url") or entry["id"]), entry)
    catalog = sorted(unique.values(), key=lambda e: (e["career_path"], e["id"]))
    by_path: dict[str, int] = {}
    for entry in catalog:
        by_path[entry["career_path"]] = by_path.get(entry["career_path"], 0) + 1
    print("total", len(catalog), by_path)
    if not args.dry_run:
        OUTPUT_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {OUTPUT_PATH.relative_to(BACKEND_ROOT)}")
    return 1 if sources and failures == len(sources) else 0


if __name__ == "__main__":
    raise SystemExit(main())
