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

from app.services.github_projects import (  # noqa: E402
    build_catalog,
    create_client,
    fetch_idea_list,
    fetch_topic,
    keep_allowed_links,
)

SOURCES_PATH = BACKEND_ROOT / "data" / "project_sources.yaml"
OUTPUT_PATH = BACKEND_ROOT / "data" / "github_projects.json"
FETCHERS = {"idea_list": fetch_idea_list, "topic": fetch_topic}


def _source_of(entry_id: str, source_ids: list[str]) -> str | None:
    # ids look like gh_<family>_<source_id>_<slug>
    rest = entry_id.split("_", 2)[-1] if entry_id.startswith("gh_") else ""
    return next((source for source in source_ids if rest.startswith(source + "_")), None)


def merge_catalog(previous: list[dict], fetched: dict[str, list[dict]],
                  configured: list[str]) -> tuple[list[dict], list[str]]:
    """The new catalog and notes to print.

    fetched maps each source synced in this run to its entries. Entries from sources not synced
    this run (a failed fetch, or --source picked others) are kept from the last run; entries from
    a source no longer in project_sources.yaml are removed. Entries are unique by id; entries
    that share a link are kept and reported, since that usually means an upstream README links
    two projects to the same place.
    """
    notes: list[str] = []
    kept: dict[str, dict] = {}
    removed = 0
    for entry in previous:
        source = _source_of(entry["id"], configured)
        if source is None:
            removed += 1
        elif source not in fetched:
            kept[entry["id"]] = entry
    if removed:
        notes.append(f"removed {removed} entries from sources no longer in project_sources.yaml")
    for source_id, entries in fetched.items():
        for entry in entries:
            if entry["id"] in kept:
                notes.append(f"duplicate id {entry['id']} ({source_id}); kept the first")
                continue
            kept[entry["id"]] = entry
    by_link: dict[tuple[str, str], list[str]] = {}
    for entry in kept.values():
        if entry.get("url"):
            by_link.setdefault((entry["career_path"], entry["url"]), []).append(entry["title"])
    for (career_path, url), titles in sorted(by_link.items()):
        if len(titles) > 1:
            notes.append(f"shared link in {career_path}: {' / '.join(sorted(titles))} -> {url}")
    return sorted(kept.values(), key=lambda e: (e["career_path"], e["id"])), notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", action="append", default=[], help="source id from project_sources.yaml")
    parser.add_argument("--dry-run", action="store_true", help="print counts without writing the file")
    args = parser.parse_args()

    configured_sources = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))["sources"]
    configured = [source["id"] for source in configured_sources]
    sources = [s for s in configured_sources if not args.source or s["id"] in args.source]

    previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")) if OUTPUT_PATH.exists() else []
    fetched: dict[str, list[dict]] = {}
    failures = 0
    with create_client(os.environ.get("GITHUB_TOKEN")) as client:
        for source in sources:
            try:
                raw = FETCHERS[source["kind"]](client, source)
            except Exception as error:  # keep last run's entries for this source
                failures += 1
                print(f"error {source['id']}: {type(error).__name__}: {error}")
                continue
            raw, skipped = keep_allowed_links(raw)
            for project in skipped:
                print(f"skip  {source['id']}: {project.title} links outside the allowed sites: {project.url}")
            entries = build_catalog(raw)
            for entry in entries:  # the copied text travels with its source and licence
                entry["source_repo"] = source.get("repo")
                entry["license"] = source.get("license")
            fetched[source["id"]] = entries
            print(f"ok    {source['id']}: {len(raw)} projects -> {len(entries)} role entries")

    catalog, notes = merge_catalog(previous, fetched, configured)
    for note in notes:
        print("note ", note)
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
