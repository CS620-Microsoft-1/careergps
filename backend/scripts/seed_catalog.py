"""Load data/certifications.json and the school_course / student_org entries of data/resources.yaml
into the catalog tables. Safe to re-run; one transaction for everything.

    python -m scripts.seed_catalog --dry-run   # report what would change, then roll back
    python -m scripts.seed_catalog             # add the rows that are missing; leave existing rows alone
    python -m scripts.seed_catalog --update    # also overwrite existing rows with the files' values

Rows that are in the database but not in the files are left alone. Prints table names and counts only.
"""
import argparse
from collections import Counter
from datetime import date

from sqlalchemy.orm import Session

from app.models.catalog import CatalogVersion
from app.services import catalog_writes
from app.services.certifications.catalog import CATALOG_PATH, load_catalog as load_certifications
from app.services.resources import load_catalog as load_resources

TABLES = {"certification": "certifications", "school_course": "school_courses", "student_org": "student_orgs"}


def seed(session: Session, *, update: bool = False) -> dict[str, Counter]:
    """Write the files into the tables (no commit). Returns {table: Counter(inserted/updated/unchanged/skipped)}."""
    certifications = load_certifications(CATALOG_PATH)
    had_version = session.get(CatalogVersion, catalog_writes.CERTIFICATIONS) is not None
    counts = {table: Counter() for table in TABLES.values()}

    def write(kind, row_id, upsert, url):
        exists = catalog_writes.get_row(session, kind, row_id) is not None
        if exists and not update:
            counts[TABLES[kind]]["skipped"] += 1
            return
        # A new row records its own url as the page it was checked against; --update keeps the stored one.
        counts[TABLES[kind]][upsert(None if exists else url)] += 1

    for item in certifications["certifications"]:
        write("certification", item.id, lambda source_url, item=item: catalog_writes.upsert_certification(
            session, item.model_dump(), verified_at=date.fromisoformat(item.last_verified), source_url=source_url),
            item.url)
    upserts = {"school_course": catalog_writes.upsert_school_course, "student_org": catalog_writes.upsert_student_org}
    for entry in load_resources():
        if entry["type"] in upserts:
            write(entry["type"], entry["id"], lambda source_url, entry=entry: upserts[entry["type"]](
                session, entry, source_url=source_url), entry.get("url"))
    # A fresh database starts at the file's version, so recommendations cached from the file stay valid.
    if not had_version:
        catalog_writes.set_catalog_version(session, catalog_writes.CERTIFICATIONS, certifications["version"])
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, then roll back")
    parser.add_argument("--update", action="store_true", help="overwrite existing rows with the files' values")
    args = parser.parse_args()

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        counts = seed(session, update=args.update)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    for table, counter in counts.items():
        print(f"{table}: " + ", ".join(f"{counter[key]} {key}" for key in ("inserted", "updated", "unchanged", "skipped")))
    print("Dry run: nothing was written." if args.dry_run else "Committed.")


if __name__ == "__main__":
    main()
