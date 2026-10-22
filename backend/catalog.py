"""The analyses HOP Audit runs and the content-integrity categories.

Keys here are stored on sites and runs; labels are what the UI shows.
"""

from typing import NamedTuple


class Analysis(NamedTuple):
    key: str
    label: str


ANALYSES = (
    Analysis("readability", "Readability"),
    Analysis("links", "Links"),
    Analysis("seo", "SEO and metadata"),
    Analysis("content_integrity", "Content integrity"),
    Analysis("summary", "Summary report"),
    Analysis("deliverables", "Prospect deliverables"),
)
ANALYSIS_KEYS = tuple(a.key for a in ANALYSES)


class Category(NamedTuple):
    code: str
    label: str


# Finding IDs carry the code as their prefix (C-01, TM-03).
INTEGRITY_CATEGORIES = (
    Category("C", "Contradictions"),
    Category("U", "Instructions that don't match"),
    Category("T", "Translation defects"),
    Category("TM", "Terminology inconsistency"),
    Category("D", "Disclosure and legal text"),
    Category("L", "Retired products"),
    Category("S", "Scope errors"),
    Category("O", "Outdated content"),
    Category("N", "Links and duplicates"),
    Category("X", "Structure and publishing errors"),
)
CATEGORY_CODES = tuple(c.code for c in INTEGRITY_CATEGORIES)
