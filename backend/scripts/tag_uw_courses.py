"""Tag UW–Madison courses with core skill_ids from their guide description, using Gemini (agy -p).

    python -m scripts.tag_uw_courses --dry-run --only 220,300         # print the prompt, call nothing
    python -m scripts.tag_uw_courses --only 220,300 --out /tmp/x.json  # a small sample
    python -m scripts.tag_uw_courses                                   # every course without tags

Reads data/uw_courses/comp_sci.json and writes {number: {"skills": [...], "quote": "..."}} to
data/uw_courses/comp_sci_skills.json (merged with what is there). Needs the agy CLI on this machine
and uses its subscription, so it is run by hand, never in CI. Every answer is checked here: skill_ids
must exist in core_catalog.json and the quote must appear in the description. Review the file
before seeding.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

from app.core.config import BACKEND_ROOT
from app.services.skill_gaps.assets import ASSET_ROOT

COURSES = BACKEND_ROOT / "data" / "uw_courses" / "comp_sci.json"
TAGS = BACKEND_ROOT / "data" / "uw_courses" / "comp_sci_skills.json"
BATCH = 20
MAX_SKILLS = 8
FAMILY_NAMES = {"software_engineer": "software engineer", "data_analyst": "data analyst", "ai_engineer": "AI engineer"}

INSTRUCTIONS = """You tag university courses with the job skills a student practices in them.
Use only the course description. Do not use tools or files; answer with JSON only.

Rules:
- Use only skill_id values from the list below. Each skill belongs to one or more roles.
- The same ability can have a different skill_id in each role. Tag every one that fits:
  SQL work is both "relational_sql" (software engineer) and "sql" (data analyst, AI engineer);
  programming in a named language other than Python is "programming" and "general_programming";
  Python is "programming" and "python"; statistics is "statistics" and "math_statistics".
- Tag a skill only when the description says the course teaches or practices it. A passing mention,
  a prerequisite, or a topic the course is merely about is not enough.
- Theory-only, seminar, thesis, research, directed-study, teaching and internship courses usually get
  no skills. An empty list is a good answer.
- At most 8 skills per course, the most central first.
- "quote": the shortest phrase copied exactly from the description that supports the tags; "" when
  the list is empty.

Answer: {"courses": [{"number": "...", "skill_ids": ["..."], "quote": "..."}]}, one entry per course,
in the order given.

Skills (skill_id | name | roles | definition):
"""


ANSWER_SCHEMA = {
    "type": "object", "required": ["courses"],
    "properties": {"courses": {"type": "array", "items": {
        "type": "object", "required": ["number", "skill_ids", "quote"],
        "properties": {"number": {"type": "string"}, "skill_ids": {"type": "array", "items": {"type": "string"}},
                       "quote": {"type": "string"}}}}},
}


def skill_table() -> tuple[str, set[str]]:
    catalog = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))
    skills: dict[str, dict] = {}
    for family, data in catalog["families"].items():
        for module in data["modules"]:
            for skill in module["skills"]:
                entry = skills.setdefault(skill["skill_id"], {**skill, "roles": []})
                entry["roles"].append(FAMILY_NAMES[family])
    lines = [f"{skill_id} | {skill['skill_name']} | {', '.join(skill['roles'])} | {skill['definition']}"
             for skill_id, skill in skills.items()]
    return "\n".join(lines), set(skills)


def prompt(courses: list[dict], table: str) -> str:
    listed = [{"number": course["number"], "code": course["course_code"], "title": course["title"],
               "description": course["description"]} for course in courses]
    return f"{INSTRUCTIONS}{table}\n\nCourses:\n{json.dumps(listed, ensure_ascii=False, indent=1)}\n"


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def check(answer: dict, courses: list[dict], known: set[str]) -> tuple[dict, list[str]]:
    """Valid tags per course number, and the problems found."""
    by_number = {course["number"]: course for course in courses}
    tags, problems = {}, []
    for item in answer.get("courses", []):
        number = str(item.get("number"))
        course = by_number.get(number)
        if course is None:
            problems.append(f"unknown course {number}")
            continue
        skills = [skill for skill in item.get("skill_ids", []) if skill in known]
        unknown = set(item.get("skill_ids", [])) - known
        if unknown:
            problems.append(f"{number}: dropped unknown skills {sorted(unknown)}")
        quote = item.get("quote") or ""
        if skills and _squash(quote) not in _squash(course["description"]):
            problems.append(f"{number}: quote not in the description: {quote!r}")
        tags[number] = {"skills": list(dict.fromkeys(skills))[:MAX_SKILLS], "quote": quote}
    for number in by_number.keys() - tags.keys():
        problems.append(f"{number}: no answer")
    return tags, problems


def ask_gemini(text: str) -> dict:
    # Run outside the repository so the agent has no project files to read.
    with tempfile.TemporaryDirectory() as workdir:
        result = subprocess.run(["agy", "-p", text, "--mode", "plan", "--disable-slash-commands",
                                 "--output-format", "json", "--json-schema", json.dumps(ANSWER_SCHEMA)],
                                cwd=workdir, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"agy exited with {result.returncode}: {result.stderr.strip()[-500:]}")
    answer = _find_answer(json.loads(result.stdout))
    if answer is None:
        raise ValueError(f"No answer in agy's output: {result.stdout[:300]!r}")
    return answer


def _find_answer(value):
    """The {"courses": [...]} object, wherever agy's JSON output puts it (possibly as a JSON string)."""
    if isinstance(value, dict):
        if isinstance(value.get("courses"), list):
            return value
        values = value.values()
    elif isinstance(value, list):
        values = value
    elif isinstance(value, str) and "courses" in value:
        start, end = value.find("{"), value.rfind("}")
        try:
            return _find_answer(json.loads(value[start:end + 1])) if 0 <= start < end else None
        except json.JSONDecodeError:
            return None
    else:
        return None
    for item in values:
        found = _find_answer(item)
        if found is not None:
            return found
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated course numbers, e.g. 220,300")
    parser.add_argument("--all", action="store_true", help="also re-tag courses that already have tags")
    parser.add_argument("--out", type=Path, default=TAGS)
    parser.add_argument("--dry-run", action="store_true", help="print the prompt; call nothing")
    args = parser.parse_args()

    courses = json.loads(COURSES.read_text(encoding="utf-8"))["courses"]
    existing = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    if args.only:
        wanted = {number.strip() for number in args.only.split(",")}
        courses = [course for course in courses if course["number"] in wanted]
    elif not args.all:
        courses = [course for course in courses if course["number"] not in existing]
    table, known = skill_table()
    batches = [courses[start:start + BATCH] for start in range(0, len(courses), BATCH)]
    if args.dry_run:
        for batch in batches:
            print(prompt(batch, table))
        print(f"# {len(courses)} courses in {len(batches)} call(s); nothing was sent.")
        return
    for index, batch in enumerate(batches, 1):
        tags, problems = check(ask_gemini(prompt(batch, table)), batch, known)
        existing.update(tags)
        args.out.write_text(json.dumps(dict(sorted(existing.items())), ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"batch {index}/{len(batches)}: {len(tags)} tagged")
        for problem in problems:
            print("  " + problem)


if __name__ == "__main__":
    main()
