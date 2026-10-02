"""
PDF -> DocumentStructure (inferred).

Most PDFs carry no structure, so headings, lists, figures and tables are
*inferred* from layout: font size and weight relative to the body text,
bullet/number markers, image objects, and ruled-table detection. Everything
produced here is marked extra["inferred"] = True. Reading order reuses
pdf_auto's column handling, so it matches what the reader already reads.

Tables follow the same "treat as images" policy as other formats: they come
out as table blocks with their text but no header structure.
"""

import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional

import pdfplumber
from pdfminer.pdftypes import resolve1

from . import ocr_pdf
from .pdf_auto import _paragraph_text, _split_paragraphs, build_repeated_lines, reading_order_groups
from .structure import Block, DocumentStructure, FIGURE, HEADING, LIST_ITEM, PARAGRAPH, TABLE

MAX_PAGES = int(os.environ.get("WEBREADER_MAX_STRUCTURE_PAGES", "400"))
MIN_FIGURE_PT = 24          # ignore icons/bullets smaller than this in either dimension
BACKGROUND_FRACTION = 0.85  # an image this much of the page is a scan/background, not a figure
HEADING_SIZE_RATIO = 1.15
_BOLD = re.compile(r"bold|black|heavy|semibold|demi", re.I)
_BULLET = re.compile(r"^(?:[•◦▪■●○‣·\-–—*]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)])\s+")


def _line_stats(line):
    chars = sum(len(w["text"]) for w in line["words"]) or 1
    size = sum(w.get("size", 0) * len(w["text"]) for w in line["words"]) / chars
    bold = sum(len(w["text"]) for w in line["words"] if _BOLD.search(w.get("fontname", "") or "")) / chars
    return size, bold, chars


def _para_stats(lines):
    size = bold = chars = 0.0
    for ln in lines:
        s, b, c = _line_stats(ln)
        size += s * c; bold += b * c; chars += c
    chars = chars or 1
    return size / chars, bold / chars, chars


def _bbox_rows(table) -> List[List[str]]:
    try:
        return [[(c or "").strip() for c in row] for row in table.extract()]
    except Exception:
        return []


def extract_pdf_structure(path: str, max_pages: Optional[int] = None) -> DocumentStructure:
    max_pages = max_pages or MAX_PAGES
    sizes: Dict[str, Counter] = {"text": Counter(), "ocr": Counter()}  # OCR box heights aren't font sizes
    pages: List[List[Dict[str, Any]]] = []
    ocr_confidence: Dict[int, float] = {}

    with pdfplumber.open(path) as pdf:
        cat = pdf.doc.catalog or {}
        mark = resolve1(cat.get("MarkInfo")) or {}
        tagged = bool((resolve1(mark.get("Marked")) if isinstance(mark, dict) else False)
                      and cat.get("StructTreeRoot") is not None)
        lang = resolve1(cat.get("Lang"))
        lang = lang.decode("latin-1") if isinstance(lang, bytes) else (lang or "")
        title = str((pdf.metadata or {}).get("Title") or "").strip()
        total = len(pdf.pages)
        image_only: List[int] = []
        repeated = build_repeated_lines(pdf)
        key = ocr_pdf.file_key(path)
        try:
            plan = ocr_pdf.plan_ocr(pdf, key, max_pages=max_pages)
        except Exception:
            plan = ocr_pdf.OcrPlan()

        for n, page in enumerate(pdf.pages[:max_pages], 1):
            items: List[Dict[str, Any]] = []
            src, source = page, "text"
            if (n - 1) in plan.ocr_pages:
                try:
                    src, source = ocr_pdf.ocr_page(page, key), "ocr"
                    ocr_confidence[n] = round(src.mean_conf, 1)
                except Exception:
                    src, source = page, "text"
            try:
                tables = page.find_tables() if source == "text" else []   # ruled-table detection needs a real text layer
            except Exception:
                tables = []
            boxes = [t.bbox for t in tables]  # (x0, top, x1, bottom)

            for group in reading_order_groups(src, repeated if source == "text" else set(), exclude_bboxes=boxes,
                                              extra_attrs=("fontname", "size")):
                for para in _split_paragraphs(group):
                    size, bold, chars = _para_stats(para)
                    sizes[source][round(size * 2) / 2] += chars
                    items.append({"k": "para", "lines": para, "size": size, "bold": bold, "top": para[0]["top"],
                                  "x0": para[0]["x0"], "page": n, "src": source})

            extras: List[Dict[str, Any]] = []
            for t in tables:
                rows = _bbox_rows(t)
                if any(any(c for c in r) for r in rows):
                    extras.append({"k": "table", "rows": rows, "top": t.bbox[1], "bbox": list(t.bbox), "page": n})
            page_area = float(page.width) * float(page.height)
            has_text = any(i["k"] == "para" for i in items)
            for im in page.images:
                w, h = im["x1"] - im["x0"], im["bottom"] - im["top"]
                if w < MIN_FIGURE_PT or h < MIN_FIGURE_PT:
                    continue
                if w * h >= BACKGROUND_FRACTION * page_area:
                    if not has_text:
                        image_only.append(n)   # a scanned page, not a figure
                    continue
                extras.append({"k": "figure", "top": im["top"], "bbox": [im["x0"], im["top"], im["x1"], im["bottom"]], "page": n})

            # Slot tables/figures into reading order by vertical position.
            for ex in sorted(extras, key=lambda e: e["top"]):
                pos = next((i for i, it in enumerate(items) if it["top"] > ex["top"]), len(items))
                items.insert(pos, ex)
            pages.append(items)

    body_by_src = {k: (c.most_common(1)[0][0] if c else 0.0) for k, c in sizes.items()}
    body = body_by_src["text"] or body_by_src["ocr"]

    def body_of(it) -> float:
        return body_by_src.get(it.get("src", "text")) or body

    def ratio(it) -> float:  # size relative to this page's own body text, so OCR and text pages are comparable
        b = body_of(it)
        return round((it["size"] / b) * 20) / 20 if b else 0.0

    # Rank distinct heading sizes (largest = level 1)
    def looks_like_heading(it) -> bool:
        lines = it["lines"]
        text = _paragraph_text(lines)
        words = len(text.split())
        if not text or len(lines) > 3 or words > 25 or text.rstrip().endswith((".", ",", ";", ":")):
            return False
        if _BULLET.match(text):
            return False
        big = body_of(it) and it["size"] >= body_of(it) * HEADING_SIZE_RATIO
        bold_short = it["bold"] >= 0.6 and words <= 14
        caps = text.isupper() and words <= 10 and len(text) > 3 and it["bold"] >= 0.6
        return bool(big or bold_short or caps)

    heading_sizes = sorted({ratio(it) for p in pages for it in p
                            if it["k"] == "para" and looks_like_heading(it) and body_of(it) and it["size"] >= body_of(it) * HEADING_SIZE_RATIO},
                           reverse=True)
    max_level = min(len(heading_sizes), 5)

    def level_of(it) -> int:
        r = ratio(it)
        if r in heading_sizes:
            return min(heading_sizes.index(r) + 1, 6)
        return min(max_level + 1, 6)  # bold/caps at body size: below the sized headings

    s = DocumentStructure(format="pdf", title=title, language=lang, metadata={
        "tagged": tagged, "pages": total, "analysed_pages": min(total, max_pages), "truncated": total > max_pages,
        "image_only_pages": image_only, "body_font_size": body,
        # OCR fallback bookkeeping (1-based page numbers)
        "ocr_pages": sorted(i + 1 for i in plan.ocr_pages), "ocr_reasons": {str(i + 1): r for i, r in plan.reasons.items()},
        "unreliable_layer": plan.unreliable_layer, "text_agreement": [round(a, 2) for a in plan.agreement],
        "ocr_confidence": {str(k): v for k, v in ocr_confidence.items()},
        "ocr_low_confidence_pages": sorted(k for k, v in ocr_confidence.items() if v < ocr_pdf.LOW_CONFIDENCE)})

    for items in pages:
        for it in items:
            loc = f"Page {it['page']}"
            inferred = {"inferred": True, "page": it["page"]}
            if it["k"] == "table":
                s.blocks.append(Block(kind=TABLE, rows=it["rows"], location=loc, extra={**inferred, "bbox": it["bbox"]}))
            elif it["k"] == "figure":
                s.blocks.append(Block(kind=FIGURE, figure_type="picture", location=loc, extra={**inferred, "bbox": it["bbox"]}))
            elif looks_like_heading(it):
                s.blocks.append(Block(kind=HEADING, text=_paragraph_text(it["lines"]), level=level_of(it), location=loc,
                                      extra={**inferred, "font_size": round(it["size"], 1), "bold": it["bold"] >= 0.6}))
            else:
                _emit_paragraph_or_list(s, it, loc, inferred)
    return s


def _emit_paragraph_or_list(s: DocumentStructure, it, loc, inferred):
    lines = it["lines"]
    if not any(_BULLET.match(l["text"].strip()) for l in lines):
        s.blocks.append(Block(kind=PARAGRAPH, text=_paragraph_text(lines), location=loc, extra=inferred))
        return
    current: List[Dict[str, Any]] = []
    kind = PARAGRAPH

    def flush():
        nonlocal current
        if current:
            text = _paragraph_text(current)
            if kind == LIST_ITEM:
                text = _BULLET.sub("", text, count=1)
            s.blocks.append(Block(kind=kind, text=text, location=loc, extra=inferred))
        current = []

    for ln in lines:
        if _BULLET.match(ln["text"].strip()):
            flush(); kind = LIST_ITEM
        current.append(ln)
    flush()
