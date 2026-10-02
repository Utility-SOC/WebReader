"""
Inspect an existing PDF tag tree (the structure a screen reader actually uses).

Many PDFs are "tagged" automatically by a word processor's export and are
still inaccessible: figures with no alt text, headings tagged as plain
paragraphs or skipping levels, text that never made it into the tag tree,
custom tags with no mapping to a standard type. This reads the tree and
reports what it finds, in the same Issue format as the other checks.

Scope: the checks a mechanical pass can make (a subset of what PDF/UA
validators such as veraPDF test). Passing them doesn't make a PDF accessible.
Tables follow the same "treat as images" policy as everywhere else.
"""

import os
import re
from typing import Any, Dict, List, Tuple

import pdfplumber
from pdfminer.pdftypes import resolve1
from pdfplumber.structure import PDFStructTree, StructTreeMissing

from .a11y_checks import (ERROR, INFO, WARNING, Issue, _FILENAME_ALT, _GENERIC_NAME, _REDUNDANT_PREFIX, MAX_ALT_CHARS)
from .structure import tables_as_images

MAX_PAGES = int(os.environ.get("WEBREADER_MAX_STRUCTURE_PAGES", "400"))
COVERAGE_SAMPLE_PAGES = 40
UNTAGGED_TEXT_THRESHOLD = 0.05   # more than 5% of text outside the tag tree is worth reporting
MAX_ISSUES_PER_CODE = 200        # a 400-page book can have thousands of equally-broken figures; list the first
                                 # ones in full and report the true total (facts["issue_totals"])

# Standard structure types (PDF 1.7 + the common PDF 2.0 additions).
STANDARD_TYPES = {
    "Document", "DocumentFragment", "Part", "Art", "Sect", "Div", "BlockQuote", "Caption", "TOC", "TOCI", "Index",
    "NonStruct", "Private", "P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "L", "LI", "Lbl", "LBody", "Table", "TR",
    "TH", "TD", "THead", "TBody", "TFoot", "Span", "Quote", "Note", "Reference", "BibEntry", "Code", "Link", "Annot",
    "Ruby", "RB", "RT", "RP", "Warichu", "WT", "WP", "Figure", "Formula", "Form", "Aside", "Title", "FENote", "Sub",
    "Em", "Strong", "Artifact",
}
_HEADING = re.compile(r"^H([1-6])$")


class _TolerantStructTree(PDFStructTree):
    """pdfplumber's reader assumes attribute objects are fully resolved dicts; real Word-exported
    PDFs keep them behind indirect references in the ClassMap, which crashes it. Nothing here uses
    element attributes, so a malformed one is ignored instead of aborting the whole inspection."""

    def _make_attributes(self, obj, revision):
        try:
            return super()._make_attributes(obj, revision)
        except Exception:
            return {}


def _name(v) -> str:
    return v.name if hasattr(v, "name") else str(v)


def _walk(els):
    for el in els:
        yield el
        yield from _walk(el.children)


def _resolve_role(t: str, role_map: Dict[str, str]) -> str:
    for _ in range(8):  # follow a custom tag's mapping to a standard type
        if t in STANDARD_TYPES or t not in role_map:
            return t
        t = role_map[t]
    return t


def inspect_tags(path: str) -> Tuple[Dict[str, Any], List[Issue]]:
    facts: Dict[str, Any] = {}
    issues: List[Issue] = []
    totals: Dict[str, int] = {}

    def add(issue: Issue) -> None:
        totals[issue.code] = totals.get(issue.code, 0) + 1
        if totals[issue.code] <= MAX_ISSUES_PER_CODE:
            issues.append(issue)

    with pdfplumber.open(path) as pdf:
        cat = pdf.doc.catalog or {}
        vp = resolve1(cat.get("ViewerPreferences")) or {}
        facts["display_doc_title"] = bool(resolve1(vp.get("DisplayDocTitle"))) if isinstance(vp, dict) else False
        try:
            tree = _TolerantStructTree(pdf)
        except StructTreeMissing:
            facts["tag_tree"] = False
            return facts, issues
        facts["tag_tree"] = True
        role_map = {_name(k): _name(v) for k, v in (tree.role_map or {}).items()}

        elements = list(_walk(tree.children))
        facts["tag_elements"] = len(elements)
        by_type: Dict[str, int] = {}
        nonstandard = set()
        for el in elements:
            t = _resolve_role(el.type, role_map)
            by_type[t] = by_type.get(t, 0) + 1
            if t not in STANDARD_TYPES:
                nonstandard.add(el.type)
        facts["tag_counts"] = by_type

        def loc(el) -> str:
            return f"Page {el.page_number}" if el.page_number else ""

        def where(el, code: str) -> Dict[str, Any]:
            if totals.get(code, 0) >= MAX_ISSUES_PER_CODE:
                return {}  # past the listing cap; skip the (slow) bbox lookup
            try:
                return {"bbox": list(tree.element_bbox(el))}
            except Exception:
                return {}

        # --- figures: alt text
        for el in elements:
            if _resolve_role(el.type, role_map) != "Figure":
                continue
            alt = (el.alt_text or el.actual_text or "").strip()
            if not alt:
                add(Issue("FIG_ALT_MISSING", ERROR, "A figure in the tag tree has no alternative text.",
                                    loc(el), "1.1.1", "suggest", where(el, "FIG_ALT_MISSING")))
            elif _FILENAME_ALT.search(alt) or _GENERIC_NAME.match(alt):
                add(Issue("FIG_ALT_PLACEHOLDER", ERROR,
                                    f"A figure's alternative text ('{alt[:80]}') looks like a file or shape name, not a description.",
                                    loc(el), "1.1.1", "suggest", {"alt": alt[:200], **where(el, "FIG_ALT_PLACEHOLDER")}))
            else:
                if len(alt) > MAX_ALT_CHARS:
                    add(Issue("FIG_ALT_LONG", WARNING, f"A figure's alternative text is {len(alt)} characters.",
                                        loc(el), "1.1.1", "manual", {"length": len(alt)}))
                if _REDUNDANT_PREFIX.match(alt):
                    add(Issue("FIG_ALT_REDUNDANT", INFO,
                                        f"A figure's alternative text starts with '{alt.split()[0]} of'; screen readers already announce it as a figure.",
                                        loc(el), "1.1.1", "auto"))

        # --- headings
        heads = []
        generic_h = []
        for el in elements:
            t = _resolve_role(el.type, role_map)
            m = _HEADING.match(t)
            if m:
                heads.append((int(m.group(1)), el))
            elif t == "H":
                generic_h.append(el)
        if generic_h:
            add(Issue("PDF_GENERIC_HEADING", WARNING,
                                f"{len(generic_h)} heading(s) use the generic 'H' tag, which hides their level; use H1-H6.",
                                loc(generic_h[0]), "1.3.1", "suggest", {"count": len(generic_h)}))
        prev = 0
        for level, el in heads:
            if prev and level > prev + 1:
                add(Issue("HEADING_SKIP", WARNING, f"Heading level jumps from {prev} to {level}.",
                                    loc(el), "1.3.1", "suggest", {"from": prev, "to": level}))
            prev = level
        if heads and heads[0][0] != 1:
            add(Issue("PDF_FIRST_HEADING_NOT_H1", WARNING,
                                f"The first heading is H{heads[0][0]}, not H1.", loc(heads[0][1]), "1.3.1", "suggest"))
        if not heads and not generic_h and len(pdf.pages) > 2:
            add(Issue("NO_HEADINGS", WARNING,
                                f"The tagged PDF has {len(pdf.pages)} pages and no headings, so it can't be navigated by section.",
                                wcag="1.3.1", fix="suggest"))

        # --- tables (policy: described like figures; structured mode checks header cells)
        for el in elements:
            if _resolve_role(el.type, role_map) != "Table":
                continue
            if tables_as_images():
                if not (el.alt_text or el.actual_text or "").strip():
                    add(Issue("TABLE_DESCRIPTION_MISSING", ERROR, "A table in the tag tree has no description for assistive technology.",
                                        loc(el), "1.1.1", "suggest", where(el, "TABLE_DESCRIPTION_MISSING")))
            elif not any(_resolve_role(d.type, role_map) == "TH" for d in _walk(el.children)):
                add(Issue("TABLE_NO_HEADER", ERROR, "A table has no header cells (TH).",
                                    loc(el), "1.3.1", "suggest", where(el, "TABLE_NO_HEADER")))

        # --- custom tags without a mapping to a standard type
        if nonstandard:
            names = sorted(nonstandard)[:8]
            add(Issue("PDF_NONSTANDARD_TAG", WARNING,
                                "Tags with no mapping to a standard structure type: " + ", ".join(names) +
                                (" ..." if len(nonstandard) > len(names) else "") + ".",
                                wcag="1.3.1", fix="manual", detail={"tags": sorted(nonstandard)}))

        # --- text that never made it into the tag tree (sampled)
        total = outside = 0
        bad_pages: List[int] = []
        for page in pdf.pages[: min(COVERAGE_SAMPLE_PAGES, MAX_PAGES)]:
            p_total = p_out = 0
            for ch in page.chars:
                if not ch["text"].strip():
                    continue
                p_total += 1
                if ch.get("mcid") is None and ch.get("tag") != "Artifact":
                    p_out += 1
            total += p_total; outside += p_out
            if p_total and p_out / p_total > UNTAGGED_TEXT_THRESHOLD:
                bad_pages.append(page.page_number)
        facts["untagged_text_fraction"] = round(outside / total, 3) if total else 0.0
        if total >= 50 and outside / total > UNTAGGED_TEXT_THRESHOLD:
            add(Issue("PDF_UNTAGGED_CONTENT", ERROR,
                                f"About {round(100 * outside / total)}% of the text isn't part of the tag tree (and isn't marked as decoration), "
                                "so assistive technology may skip it.",
                                f"Page {bad_pages[0]}" if bad_pages else "", "1.3.1", "suggest", {"pages": bad_pages[:20]}))
    facts["issue_totals"] = totals
    over = {c: n for c, n in totals.items() if n > MAX_ISSUES_PER_CODE}
    if over:
        facts["issues_truncated"] = over
    return facts, issues
