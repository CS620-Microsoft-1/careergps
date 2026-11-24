"""Restore the exact detail-span instruction without changing v6 contracts."""

PROMPT_REFINEMENT_VERSION = "fixed-fields-exact-detail-span.v1"

ANCHOR = (
    "Actual reference material belongs in detail, which may also name a check "
    "case, criterion or observation from that same check."
)

REPLACEMENT = (
    "Actual reference material belongs in detail. Choose ONE sufficient "
    "reference, check case, criterion or observation from that same check and "
    "copy it as a SINGLE contiguous EXACT substring of ONE cited quote. Do not "
    "join separate spans, concatenate excerpts, paraphrase or add words. Use "
    "an empty string if no qualifying detail is stated."
)


def refine_instructions(instructions):
    """Replace exactly one frozen v6 sentence; reject drift or double application."""
    if not isinstance(instructions, str):
        raise TypeError("Instructions must be a string")
    if instructions.count(ANCHOR) != 1:
        raise ValueError("Expected exactly one frozen v6 detail instruction")
    return instructions.replace(ANCHOR, REPLACEMENT, 1)
