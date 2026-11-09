"""UW–Madison courses from the course guide (data/uw_courses), as school_course entries.

Each subject has two files: <subject>.json from scripts/parse_uw_guide.py and <subject>_skills.json
from scripts/tag_uw_courses.py (reviewed by hand). Every course is kept, also those with no skills
(seminars, research): they close no gap, so they never show up as a way to close one.
resources.load_catalog() adds these entries to data/resources.yaml's, so scripts/seed_catalog.py
writes them to school_courses and the file fallback lists them too.
"""
import json

from app.core.config import BACKEND_ROOT

DATA_DIR = BACKEND_ROOT / "data" / "uw_courses"
SCHOOL = "University of Wisconsin–Madison"
# Guide subject slug → (subject code in titles, id prefix). Ids never change once seeded.
SUBJECTS = {"comp_sci": ("COMP SCI", "uw-cs")}


def meta(credits: str, last_taught: str | None) -> str:
    """"3 credits · Last taught Fall 2025"."""
    text = f"{credits} credit" + ("" if credits == "1" else "s")
    return f"{text} · Last taught {last_taught}" if last_taught else text


def course_entries() -> list[dict]:
    entries = []
    for slug, (subject, prefix) in SUBJECTS.items():
        courses_path, tags_path = DATA_DIR / f"{slug}.json", DATA_DIR / f"{slug}_skills.json"
        if not courses_path.exists() or not tags_path.exists():
            continue
        courses = json.loads(courses_path.read_text(encoding="utf-8"))["courses"]
        tags = json.loads(tags_path.read_text(encoding="utf-8"))
        for course in courses:
            skills = tags.get(course["number"], {}).get("skills", [])
            entries.append({
                "id": f"{prefix}-{course['number']}",
                "type": "school_course",
                "title": f"{subject} {course['number']}: {course['title']}",
                "provider": "UW–Madison course",
                "meta": meta(course["credits"], course["last_taught"]),
                "description": course["description"],
                "skills": skills,
                "school": SCHOOL,
                "url": course["url"],
                "course_code": course["course_code"],
                "credits": course["credits"],
                "last_taught": course["last_taught"],
            })
    return entries
