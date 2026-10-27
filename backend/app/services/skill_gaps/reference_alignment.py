"""Bounded string alignment, never a semantic or numerical evidence repair."""
import re

_NUMBER = re.compile(r"(?<![\w.])[-+\u2212]?(?:\d+(?:[.,]\d+)*|\.\d+)(?:[eE][-+]?\d+)?(?!\d|\.\d)")


def _word_character(char):
    return bool(char) and (char.isalnum() or char in "_-/+\u2212\u00b1")


def literal_spans(text, quote):
    """Return all original occurrences; a partial word is never a repair target."""
    if (not isinstance(text, str) or not isinstance(quote, str)
            or not any(char.isalnum() for char in quote)):
        return []
    numbers = [match.span() for match in _NUMBER.finditer(text)]
    spans, offset = [], 0
    while (start := text.find(quote, offset)) >= 0:
        offset = start + 1
        end = start + len(quote)
        left = start > 0 and (_word_character(text[start - 1]) or (
            text[start - 1] == "." and start > 1 and _word_character(text[start - 2])))
        right = end < len(text) and (_word_character(text[end]) or (
            text[end] == "." and end + 1 < len(text) and _word_character(text[end + 1])))
        leading = quote[0].isalnum() or quote[0] in "_-./+\u2212\u00b1"
        trailing = quote[-1].isalnum() or quote[-1] in "_-./+\u2212\u00b1"
        bounded = not (
            leading and left or trailing and right
            or any(a < start < b or a < end < b for a, b in numbers)
        )
        # Count invalid occurrences too: another occurrence must not become an
        # invisible alternative to the exact span emitted by the normal checker.
        spans.append({"start": start, "end": end, "bounded": bounded})
    return spans


def _outside_literal(text):
    brackets, quoted, escaped = [], None, False
    pairs = {")": "(", "]": "[", "}": "{"}
    for position, char in enumerate(text):
        if quoted is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quoted:
                quoted = None
        elif char in {'"', '`'} or (char == "'" and (position == 0 or not text[position - 1].isalnum())):
            quoted = char
        elif char in "([{":
            brackets.append(char)
        elif char in pairs and brackets and brackets[-1] == pairs[char]:
            brackets.pop()
    return quoted is None and not brackets


def _sentence_start(text, start):
    prefix = text[:start]
    if not prefix.strip():
        return True
    return (bool(prefix[-1:].isspace()) and prefix.rstrip().endswith((".", "!", "?"))
            and _outside_literal(prefix))


def _edge_ellipsis(quote):
    value = quote
    for marker in ("...", "\u2026"):
        if value.startswith(marker):
            value = value[len(marker):].lstrip(" \t")
            break
    for marker in ("...", "\u2026"):
        if value.endswith(marker):
            value = value[:-len(marker)].rstrip(" \t")
            break
    return value if value.strip() and value != quote else None


def _initial_case_variant(quote):
    # A plain prose word followed by whitespace. No case folding of acronyms,
    # camelCase, identifiers, backticks, numeric values or interior characters.
    if not re.match(r"^[A-Za-z][a-z]{2,}(?=\s)", quote):
        return None
    if re.match(r"^[A-Za-z]+\s+(?:[=.:()\[\]{}]|->)", quote):
        return None
    return quote[0].swapcase() + quote[1:]


def format_candidates(text, quote, comma_restorer):
    """Unique spans for outside ellipsis / initial case / existing prose commas.

    These candidates are restricted to the already-referenced source unit. A
    wrong ID is handled separately using unchanged exact text in sibling units.
    """
    variants = [(quote, [])]
    stripped = _edge_ellipsis(quote)
    if stripped is not None:
        variants.append((stripped, ["exterior_ellipsis_removed"]))
    for value, rules in list(variants):
        changed = _initial_case_variant(value)
        if changed is not None:
            variants.append((changed, [*rules, "sentence_initial_case_restored"]))
    candidates = {}
    for value, rules in variants:
        spans = literal_spans(text, value)
        options = []
        if len(spans) == 1 and spans[0]["bounded"]:
            options.append((value, spans[0], rules))
        restored = comma_restorer(text, value)
        if restored is not None:
            original, span = restored
            occurrences = literal_spans(text, original)
            if len(occurrences) == 1 and occurrences[0]["bounded"]:
                options.append((original, span, [*rules, "omitted_comma_restored"]))
        for original, span, applied in options:
            if not applied or original == quote:
                continue
            if "sentence_initial_case_restored" in applied and not _sentence_start(text, span["start"]):
                continue
            key = (span["start"], span["end"])
            candidates.setdefault(key, {"quote": original, "start": span["start"],
                                        "end": span["end"], "rules": applied})
    return list(candidates.values())


def alignment_candidates(index, unit_id, activity_id, quote, comma_restorer):
    """No cross-activity or approximate cross-unit matching; no guessed IDs."""
    unit = index.get(unit_id)
    if unit is None or unit["kind"] != "claim" or unit["activity_id"] != activity_id:
        return []
    candidates = [{**item, "unit_id": unit_id}
                  for item in format_candidates(unit["text"], quote, comma_restorer)]
    for sibling_id, sibling in index.items():
        if (sibling_id == unit_id or sibling["kind"] != "claim"
                or sibling["activity_id"] != activity_id):
            continue
        spans = literal_spans(sibling["text"], quote)
        # Preserve ambiguity even when the same text occurs twice in one unit.
        for span in spans:
            candidates.append({"unit_id": sibling_id, "quote": quote,
                               "start": span["start"], "end": span["end"],
                               "rules": [], "bounded": span["bounded"]})
    return candidates
