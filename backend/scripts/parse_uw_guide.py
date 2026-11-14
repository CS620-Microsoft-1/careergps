"""Turn a saved UW–Madison course guide subject page into data/uw_courses/<subject>.json.

    python -m scripts.parse_uw_guide "<saved page>.html" data/uw_courses/comp_sci.json

The page is https://guide.wisc.edu/courses/<subject>/ saved from a browser ("Webpage, HTML Only"),
or a Wayback Machine copy of it; links are written back to guide.wisc.edu. Keeps the course code,
title, credits, description and Last Taught of every course. Prerequisites are not kept. Skill tags
live in a separate file (scripts/tag_uw_courses.py). Standard library only.
"""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re

GUIDE = "https://guide.wisc.edu"
_WAYBACK = re.compile(r"https?://web\.archive\.org/web/(\d{8})\d*[a-z_]*/(https?://guide\.wisc\.edu[^\s\"'<>]*)")
_SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
# Kept upper case when the guide's all-caps title is title-cased.
_UPPER = re.compile(r"^(?:I{1,3}|IV|AI|VLSI|K-12|WES-CS|UX|NLP|HCI|II)$")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("​", "").replace("\xa0", " ")).strip()


def title_case(text: str) -> str:
    """"DATABASE MANAGEMENT SYSTEMS: DESIGN AND IMPLEMENTATION" → "Database Management Systems: Design and Implementation"."""
    words = text.split(" ")
    result = []
    for index, word in enumerate(words):
        core = word.strip("():,")
        start = index == 0 or result[-1].endswith(":")
        if _UPPER.match(core):
            result.append(word)
        elif core.lower() in _SMALL_WORDS and not start:
            result.append(word.lower())
        else:
            result.append("-".join(part[:1].upper() + part[1:].lower() if not _UPPER.match(part) else part
                                   for part in word.split("-")))
    return " ".join(result)


class _GuidePage(HTMLParser):
    """Collects the text of each courseblock's title, credits, description and extras."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self._field: str | None = None
        self._depth = 0  # div nesting inside the current courseblock

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if tag == "div" and "courseblock" in classes:
            self.blocks.append({"code": "", "title": "", "credits": "", "desc": "", "extra": ""})
            self._depth = 1
            return
        if not self._depth:
            return
        if tag == "div":
            self._depth += 1
        if tag == "span" and "courseblockcode" in classes:
            self._field = "code"
        elif tag == "p" and "courseblocktitle" in classes:
            self._field = "title"
        elif tag == "p" and "courseblockcredits" in classes:
            self._field = "credits"
        elif tag == "p" and "courseblockdesc" in classes:
            self._field = "desc"
        elif tag == "p" and "courseblockextra" in classes:
            self._field = "extra"
            self.blocks[-1]["extra"] += "\n"

    def handle_endtag(self, tag):
        if not self._depth:
            return
        if tag == "span" and self._field == "code":
            self._field = "title"
        elif tag == "p":
            self._field = None
        elif tag == "div":
            self._depth -= 1

    def handle_data(self, data):
        if self._depth and self._field:
            self.blocks[-1][self._field] += data


def _extra(extra: str, label: str) -> str | None:
    match = re.search(rf"^\s*{label}:\s*(.+)$", extra, re.MULTILINE)
    return _clean(match.group(1)) if match else None


def parse(html: str) -> dict:
    page = _GuidePage()
    page.feed(html)
    snapshot = _WAYBACK.search(html)
    courses = []
    for block in page.blocks:
        code = _clean(block["code"])
        number = re.search(r"(\d{3})$", code)
        if not number:
            raise ValueError(f"Unexpected course code: {code!r}")
        title = _clean(block["title"]).lstrip("—– -").strip()
        credits = re.fullmatch(r"([\d-]+) credits?\.", _clean(block["credits"]))
        if not credits:
            raise ValueError(f"{code}: unexpected credits {block['credits']!r}")
        courses.append({
            "number": number.group(1),
            "course_code": code,
            "title": title_case(title),
            "credits": credits.group(1),
            "description": _clean(block["desc"]),
            "last_taught": _extra(block["extra"], "Last Taught"),
        })
    return {"snapshot_date": snapshot and f"{snapshot.group(1)[:4]}-{snapshot.group(1)[4:6]}-{snapshot.group(1)[6:]}",
            "courses": courses}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("page", type=Path, help="the saved guide page")
    parser.add_argument("output", type=Path, help="e.g. data/uw_courses/comp_sci.json")
    parser.add_argument("--subject", default="comp_sci", help="the guide's subject slug (default comp_sci)")
    args = parser.parse_args()
    parsed = parse(args.page.read_text(encoding="utf-8"))
    url = f"{GUIDE}/courses/{args.subject}/"
    data = {
        "source": url,
        "retrieved": parsed["snapshot_date"],
        "note": "Parsed by scripts/parse_uw_guide.py. Prerequisites are left out on purpose.",
        "courses": [{**course, "url": url} for course in parsed["courses"]],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(data['courses'])} courses → {args.output}")


if __name__ == "__main__":
    main()
