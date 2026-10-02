"""
Accessibility checks over a DocumentStructure (and document-level checks for PDFs).

Each Issue says what is wrong, where, which WCAG success criterion it relates
to, and how it can be fixed:

  fix = "auto"     safe to fix without judgement (e.g. copy a title that exists elsewhere)
        "suggest"  a model can propose a fix (alt text, table header row, slide title)
        "manual"   needs a person

These checks find what *can* be detected mechanically. Passing them does not
make a document accessible -- alt text can be present and wrong, reading order
can be technically valid and confusing -- so the report is a list of what is
still open, never a compliance claim.
"""

import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from .structure import DocumentStructure, FIGURE, HEADING, SLIDE_TITLE, TABLE, tables_as_images

ERROR, WARNING, INFO = "error", "warning", "info"

_FILENAME_ALT = re.compile(r"(\.(png|jpe?g|gif|bmp|tiff?|webp|svg|emf|wmf)$)|^(img|image|picture|pic|screenshot|dsc|photo)[\s_\-]*\d*$", re.I)
_GENERIC_NAME = re.compile(r"^(picture|image|chart|graphic|content placeholder|object|shape|diagram|media)\s*\d*$", re.I)
_REDUNDANT_PREFIX = re.compile(r"^(image|picture|photo|graphic)\s+(of|showing)\b", re.I)
MAX_ALT_CHARS = 250


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    location: str = ""
    wcag: str = ""            # success criterion, e.g. "1.1.1"
    fix: str = "manual"
    detail: Dict[str, Any] = None

    def to_dict(self):
        d = asdict(self)
        if d["detail"] is None:
            d["detail"] = {}
        return d


def analyze(s: DocumentStructure) -> List[Issue]:
    issues: List[Issue] = []

    if not s.title:
        issues.append(Issue("DOC_TITLE_MISSING", ERROR, "The document has no title in its properties.",
                            wcag="2.4.2", fix="auto"))
    if not s.language:
        issues.append(Issue("DOC_LANGUAGE_MISSING", ERROR, "The document's language is not set.",
                            wcag="3.1.1", fix="suggest"))

    _check_figures(s, issues)
    _check_tables(s, issues)
    if s.format == "docx":
        _check_headings(s, issues)
    if s.format == "pptx":
        _check_slides(s, issues)
    return issues


def _check_figures(s, issues):
    for b in s.blocks:
        if b.kind != FIGURE or b.decorative:
            continue
        alt = (b.alt_text or "").strip()
        label = f"{b.figure_type or 'image'}" + (f" '{b.name}'" if b.name else "")
        if not alt:
            issues.append(Issue("FIG_ALT_MISSING", ERROR, f"The {label} has no alternative text.",
                                b.location, "1.1.1", "suggest", {"figure_type": b.figure_type, "name": b.name}))
        elif _FILENAME_ALT.search(alt) or _GENERIC_NAME.match(alt):
            issues.append(Issue("FIG_ALT_PLACEHOLDER", ERROR,
                                f"The {label}'s alternative text ('{alt}') looks like a file or shape name, not a description.",
                                b.location, "1.1.1", "suggest", {"alt": alt}))
        else:
            if len(alt) > MAX_ALT_CHARS:
                issues.append(Issue("FIG_ALT_LONG", WARNING,
                                    f"The {label}'s alternative text is {len(alt)} characters; consider a short alt text plus a longer description.",
                                    b.location, "1.1.1", "manual", {"length": len(alt)}))
            if _REDUNDANT_PREFIX.match(alt):
                issues.append(Issue("FIG_ALT_REDUNDANT", INFO,
                                    f"The {label}'s alternative text starts with '{alt.split()[0]} of'; screen readers already announce it as an image.",
                                    b.location, "1.1.1", "auto"))


def _check_tables(s, issues):
    if tables_as_images():
        # Treated like figures: the table needs a description a screen-reader user can use
        # instead of walking its cells. (Existing alt text is checked like any other.)
        for b in s.blocks:
            if b.kind != TABLE or not any(any(c for c in r) for r in b.rows):
                continue
            alt = (b.alt_text or "").strip()
            size = f"{len(b.rows)} rows by {max(len(r) for r in b.rows)} columns"
            if not alt:
                issues.append(Issue("TABLE_DESCRIPTION_MISSING", ERROR,
                                    f"The table ({size}) has no description for assistive technology.",
                                    b.location, "1.1.1", "suggest", {"rows": len(b.rows), "table_text": b.rows[:20]}))
            elif _FILENAME_ALT.search(alt) or _GENERIC_NAME.match(alt):
                issues.append(Issue("TABLE_DESCRIPTION_PLACEHOLDER", ERROR,
                                    f"The table's description ('{alt}') looks like a placeholder, not a description.",
                                    b.location, "1.1.1", "suggest", {"alt": alt}))
        return
    for b in s.blocks:
        if b.kind != TABLE or not b.rows or len(b.rows) < 2:
            continue
        if not b.header_row:
            style_only = b.extra.get("header_row_style")
            msg = "The table has no header row marked for assistive technology."
            if style_only:
                msg += " (A header-row style is applied, but it is not marked as a repeating header row.)"
            issues.append(Issue("TABLE_NO_HEADER", ERROR, msg, b.location, "1.3.1", "suggest",
                                {"first_row": b.rows[0][:6]}))
        if b.extra.get("merged"):
            issues.append(Issue("TABLE_MERGED_CELLS", WARNING,
                                "The table has merged or split cells, which many screen readers handle poorly.",
                                b.location, "1.3.1", "manual"))
        if any(not any(c for c in r) for r in b.rows):
            issues.append(Issue("TABLE_EMPTY_ROW", WARNING, "The table has an entirely empty row.",
                                b.location, "1.3.1", "manual"))


def _check_headings(s, issues):
    heads = s.headings()
    words = sum(len(b.text.split()) for b in s.blocks if b.kind not in (FIGURE, TABLE))
    if not heads and words > 300:
        issues.append(Issue("NO_HEADINGS", WARNING,
                            f"The document has about {words} words and no headings, so it can't be navigated by section.",
                            wcag="1.3.1", fix="suggest"))
    prev = 0
    for h in heads:
        if prev and h.level > prev + 1:
            issues.append(Issue("HEADING_SKIP", WARNING,
                                f"Heading level jumps from {prev} to {h.level} at '{h.text[:50]}'.",
                                h.location, "1.3.1", "suggest", {"from": prev, "to": h.level}))
        prev = h.level


def _check_slides(s, issues):
    seen_titles: Dict[str, str] = {}
    slides = s.metadata.get("slides", {})
    order = s.metadata.get("reading_order", {})
    slide_h = s.metadata.get("slide_height", 0) or 1
    titles = {b.extra.get("slide"): b for b in s.blocks if b.kind == SLIDE_TITLE}

    for num in sorted(slides, key=int):
        info = slides[num]
        loc = f"Slide {num}"
        t = titles.get(int(num))
        if not info.get("has_title") or t is None or not t.text.strip():
            issues.append(Issue("SLIDE_TITLE_MISSING", ERROR, "The slide has no title, so it can't be found or announced in a slide list.",
                                loc, "2.4.2", "suggest", {"hidden": info.get("hidden", False)}))
        else:
            key = t.text.strip().lower()
            if key in seen_titles:
                issues.append(Issue("SLIDE_TITLE_DUPLICATE", WARNING,
                                    f"The slide title '{t.text.strip()[:50]}' is also used on {seen_titles[key]}.",
                                    loc, "2.4.2", "manual"))
            else:
                seen_titles[key] = loc

        shapes = order.get(num, [])
        # Title should be read first.
        if shapes and any(sh["kind"] == "title" for sh in shapes) and shapes[0]["kind"] != "title":
            issues.append(Issue("SLIDE_TITLE_NOT_FIRST", WARNING,
                                "The title is not first in the slide's reading order, so screen readers announce other content before it.",
                                loc, "1.3.2", "auto"))
        # Reading order vs. visual order (low confidence: layouts can legitimately differ).
        if len(shapes) > 2:
            band = max(1, slide_h // 20)
            visual = sorted(shapes, key=lambda sh: (sh["top"] // band, sh["left"]))
            if [sh["i"] for sh in visual] != [sh["i"] for sh in shapes]:
                issues.append(Issue("SLIDE_READING_ORDER", INFO,
                                    "The slide's reading order differs from its top-to-bottom, left-to-right appearance; check it reads sensibly.",
                                    loc, "1.3.2", "manual", {"confidence": "low"}))
        if info.get("hidden"):
            issues.append(Issue("SLIDE_HIDDEN", INFO, "The slide is hidden; it is still read by some assistive technology.", loc, "", "manual"))


def analyze_pdf(path: str) -> (Dict[str, Any], List[Issue]):
    """Document-level checks for a PDF: tagged? language? title? scanned?"""
    import pdfplumber
    from pdfminer.pdftypes import resolve1

    facts: Dict[str, Any] = {}
    issues: List[Issue] = []
    with pdfplumber.open(path) as pdf:
        cat = pdf.doc.catalog or {}
        mark = resolve1(cat.get("MarkInfo")) or {}
        marked = bool(resolve1(mark.get("Marked"))) if isinstance(mark, dict) else False
        facts["tagged"] = bool(marked and cat.get("StructTreeRoot") is not None)
        lang = resolve1(cat.get("Lang"))
        facts["language"] = lang.decode("latin-1") if isinstance(lang, bytes) else (lang or "")
        facts["title"] = str((pdf.metadata or {}).get("Title") or "").strip()
        facts["pages"] = len(pdf.pages)
        sample = pdf.pages[: min(5, len(pdf.pages))]
        chars = sum(len(p.chars) for p in sample)
        facts["has_text_layer"] = chars > 0

    if not facts["has_text_layer"]:
        issues.append(Issue("PDF_NO_TEXT", ERROR, "The PDF has no text layer (it looks scanned), so screen readers can't read it until it is OCR'd.",
                            wcag="1.4.5", fix="auto"))
    if not facts["tagged"]:
        issues.append(Issue("PDF_UNTAGGED", ERROR, "The PDF is not tagged, so it has no headings, lists, tables or reading order for assistive technology.",
                            wcag="1.3.1", fix="suggest"))
    if not facts["language"]:
        issues.append(Issue("PDF_LANGUAGE_MISSING", ERROR, "The PDF's language is not set.", wcag="3.1.1", fix="suggest"))
    if not facts["title"]:
        issues.append(Issue("PDF_TITLE_MISSING", ERROR, "The PDF has no title in its properties.", wcag="2.4.2", fix="auto"))
    return facts, issues


def summarize(issues: List[Issue]) -> Dict[str, Any]:
    by_sev: Dict[str, int] = {}
    by_fix: Dict[str, int] = {}
    for i in issues:
        by_sev[i.severity] = by_sev.get(i.severity, 0) + 1
        by_fix[i.fix] = by_fix.get(i.fix, 0) + 1
    return {"total": len(issues), "by_severity": by_sev, "by_fix": by_fix}
