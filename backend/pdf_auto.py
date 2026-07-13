"""
Smart automatic PDF text extraction.

Improves on plain `page.extract_text(layout=True)` by handling:
- Multi-column layouts (correct reading order: left column first, then right)
- Full-width elements (titles, abstracts) mixed with columns on the same page
- Repeated headers/footers (detected by comparing pages across the document)
- Standalone page numbers ("12", "xii", "Page 3 of 10", "- 4 -")
- Hyphenation repair across line breaks ("exam-\nple" -> "example")

Used by utils.extract_text_from_pdf_range for AUTOMATIC mode. The Manual
Layout Editor path is unaffected.
"""

import re
import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("SpeedReaderPdfAuto")

# --- Tunables -----------------------------------------------------------
HEADER_ZONE = 0.12      # loose header zone (short lines only)
FOOTER_ZONE = 0.12      # loose footer zone (short lines only)
TIGHT_ZONE = 0.08       # tight zone: any line here can be a header/footer
MAX_HF_WORDS = 12       # loose-zone header/footer lines have at most this many words
REPEAT_FRACTION = 0.4   # header/footer line must appear on >= this fraction of sampled pages
MIN_REPEAT_PAGES = 3    # documents shorter than this skip repeat detection
MAX_SAMPLE_PAGES = 30   # pages sampled for header/footer detection
MIN_GUTTER = 9.0        # min horizontal whitespace (pt) to count as a column gutter
MAX_COLUMNS = 3
WIDE_LINE_FRACTION = 0.6  # line contiguously covering > this fraction of text width = full-width
PARA_GAP_FACTOR = 1.7   # vertical gap > factor * median gap => paragraph break

# Standalone page-number lines (arabic or roman, optional decoration)
_PAGE_NUM_RE = re.compile(
    r"^[\s\-–—.·|]*((page|p\.?|pg\.?)\s*)?"
    r"(\d{1,4}|[ivxlcdm]{1,8})"
    r"(\s*(of|/)\s*\d{1,4})?[\s\-–—.·|]*$",
    re.IGNORECASE,
)

_HYPHENS = ("-", "‐", "‑", "­")


def _normalize(text: str) -> str:
    """Normalize a line for repeat detection: digits and punctuation are removed
    so 'Page 3' == 'Page 7' and OCR noise ('98 HAYES' vs '100, HAYES') collapses."""
    text = re.sub(r"[\d\W_]+", " ", text.lower(), flags=re.UNICODE)
    # Sort tokens: scanned pages sometimes yield the same header with words
    # in a different order ("BILLY BUNNY..." vs "BUNNY BILLY...")
    return " ".join(sorted(text.split()))


def _lines_from_words(words: List[Dict[str, Any]], y_tolerance: float = 3.0) -> List[Dict[str, Any]]:
    """Group pdfplumber words into visual lines by vertical position."""
    lines: List[Dict[str, Any]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        placed = False
        if lines:
            last = lines[-1]
            if abs(w["top"] - last["top"]) <= y_tolerance:
                last["words"].append(w)
                last["x1"] = max(last["x1"], w["x1"])
                last["x0"] = min(last["x0"], w["x0"])
                last["bottom"] = max(last["bottom"], w["bottom"])
                placed = True
        if not placed:
            lines.append({
                "words": [w],
                "top": w["top"], "bottom": w["bottom"],
                "x0": w["x0"], "x1": w["x1"],
            })
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
        line["text"] = " ".join(w["text"] for w in line["words"])
    return lines


def _in_hf_zone(line: Dict[str, Any], page_height: float) -> bool:
    """Header/footer zone test. The tight zone accepts any line; the loose
    zone only short lines (long lines near margins are usually body text)."""
    tight_top = line["bottom"] <= page_height * TIGHT_ZONE
    tight_bot = line["top"] >= page_height * (1.0 - TIGHT_ZONE)
    if tight_top or tight_bot:
        return True
    if len(line["words"]) > MAX_HF_WORDS:
        return False
    loose_top = line["bottom"] <= page_height * HEADER_ZONE
    loose_bot = line["top"] >= page_height * (1.0 - FOOTER_ZONE)
    return loose_top or loose_bot


def _matches_repeated(norm: str, repeated: Set[str]) -> bool:
    if not norm or not repeated:
        return False
    if norm in repeated:
        return True
    toks = set(norm.split())
    if len(toks) < 2:
        return False
    return any(
        len(set(r.split())) >= 2 and (toks <= set(r.split()) or set(r.split()) <= toks)
        for r in repeated
    )


def _is_page_number(text: str) -> bool:
    return bool(_PAGE_NUM_RE.match(text.strip())) if text.strip() else False


def build_repeated_lines(pdf) -> Set[str]:
    """
    Scan (a sample of) the document for lines that repeat in header/footer
    zones across pages. Returns a set of normalized line texts to drop.
    """
    pages = pdf.pages
    n = len(pages)
    if n < MIN_REPEAT_PAGES:
        return set()

    step = max(1, n // MAX_SAMPLE_PAGES)
    counts: Counter = Counter()
    sampled = 0
    for i in range(0, n, step):
        try:
            page = pages[i]
            h = float(page.height)
            words = page.extract_words(x_tolerance=1.5, y_tolerance=3.0)
        except Exception:
            continue
        sampled += 1
        for line in _lines_from_words(words):
            if _in_hf_zone(line, h):
                counts[_normalize(line["text"])] += 1

    if sampled < MIN_REPEAT_PAGES:
        return set()
    threshold = max(2, int(sampled * REPEAT_FRACTION))
    # OCR noise splits the same header into variants ("BILLY BUNNY AND",
    # "BILLY BUNNY AND FRIENDS"): pool counts of token-subset/superset variants.
    repeated = set()
    for t, c in counts.items():
        if not t:
            continue
        toks = set(t.split())
        if c >= threshold:
            repeated.add(t)
            continue
        if len(toks) >= 2:
            pooled = sum(
                c2 for t2, c2 in counts.items()
                if t2 and len(set(t2.split())) >= 2
                and (set(t2.split()) <= toks or toks <= set(t2.split()))
            )
            if pooled >= threshold:
                repeated.add(t)
    if repeated:
        logger.info(f"Detected {len(repeated)} repeated header/footer line(s)")
    return repeated


def _central_gaps(line: Dict[str, Any], region_x0: float, region_x1: float) -> List[Tuple[float, float]]:
    """Whitespace gaps between words of a line within the central 25-75% of the text region."""
    width = max(1.0, region_x1 - region_x0)
    lo, hi = region_x0 + 0.22 * width, region_x1 - 0.22 * width
    gaps = []
    ws = line["words"]
    for a, b in zip(ws, ws[1:]):
        g0, g1 = a["x1"], b["x0"]
        if g1 - g0 >= MIN_GUTTER and g0 < hi and g1 > lo:
            gaps.append((g0, g1))
    return gaps


def _find_gutters(words: List[Dict[str, Any]], region_x0: float, region_x1: float) -> List[float]:
    """
    Find column gutters: vertical strips in the central region with no word
    coverage. Returns split x-positions (at most MAX_COLUMNS - 1).
    """
    width = region_x1 - region_x0
    if width <= 0 or len(words) < 12:
        return []
    bins = 150
    bw = width / bins
    if bw <= 0:
        return []
    hist = [0] * bins
    for w in words:
        b0 = max(0, int((w["x0"] - region_x0) / bw))
        b1 = min(bins - 1, int((w["x1"] - region_x0) / bw))
        for b in range(b0, b1 + 1):
            hist[b] += 1

    lo_bin, hi_bin = int(bins * 0.22), int(bins * 0.78)

    # Noise tolerance: justified text or the odd wide heading may leak a few
    # words into the gutter. Bins with coverage far below typical still count.
    central = sorted(hist[lo_bin:hi_bin + 1])
    median_cov = central[len(central) // 2] if central else 0
    noise_thr = max(0, int(median_cov * 0.10))

    splits: List[float] = []
    run_start = None
    for b in range(lo_bin, hi_bin + 1):
        if hist[b] <= noise_thr:
            if run_start is None:
                run_start = b
        else:
            if run_start is not None:
                run_w = (b - run_start) * bw
                if run_w >= MIN_GUTTER:
                    splits.append(region_x0 + (run_start + (b - run_start) / 2.0) * bw)
                run_start = None
    if run_start is not None:
        run_w = (hi_bin + 1 - run_start) * bw
        if run_w >= MIN_GUTTER:
            splits.append(region_x0 + (run_start + (hi_bin + 1 - run_start) / 2.0) * bw)

    splits = splits[: MAX_COLUMNS - 1]

    # Sanity: every resulting column must hold a meaningful share of the words
    if splits:
        bounds = [region_x0] + splits + [region_x1]
        for c in range(len(bounds) - 1):
            cx0, cx1 = bounds[c], bounds[c + 1]
            n_words = sum(1 for w in words if cx0 <= (w["x0"] + w["x1"]) / 2.0 < cx1 or (c == len(bounds) - 2 and (w["x0"] + w["x1"]) / 2.0 == cx1))
            if n_words < max(6, 0.08 * len(words)):
                return []
    return splits


def _join_lines(lines: List[Dict[str, Any]]) -> str:
    """Join lines top-to-bottom with paragraph detection and dehyphenation."""
    if not lines:
        return ""
    gaps = [b["top"] - a["bottom"] for a, b in zip(lines, lines[1:])]
    positive = sorted(g for g in gaps if g >= 0)
    median_gap = positive[len(positive) // 2] if positive else 0.0

    out = ""
    for idx, line in enumerate(lines):
        text = line["text"].strip()
        if not text:
            continue
        if not out:
            out = text
            continue
        gap = gaps[idx - 1] if idx - 1 < len(gaps) else 0.0
        para = median_gap > 0 and gap > median_gap * PARA_GAP_FACTOR + 1.0
        if para:
            out += "\n\n" + text
        elif out.endswith(_HYPHENS) and text[:1].islower():
            out = out[:-1] + text  # dehyphenate
        else:
            out += " " + text
    return out


def extract_page_smart(page, repeated: Optional[Set[str]] = None) -> str:
    """
    Extract readable text from a page in natural reading order.
    Returns "" when the page has no extractable text (caller falls back to OCR).
    """
    repeated = repeated or set()
    words = page.extract_words(x_tolerance=1.5, y_tolerance=3.0)
    if not words:
        return ""
    h = float(page.height)

    # 1. Build visual lines, drop headers/footers and page numbers
    kept: List[Dict[str, Any]] = []
    for line in _lines_from_words(words):
        if _in_hf_zone(line, h) and _matches_repeated(_normalize(line["text"]), repeated):
            continue
        # Page numbers get a slightly wider margin zone
        near_edge = line["bottom"] <= h * (HEADER_ZONE * 1.5) or line["top"] >= h * (1.0 - FOOTER_ZONE * 1.5)
        if near_edge and _is_page_number(line["text"]):
            continue
        kept.append(line)
    if not kept:
        return ""

    region_x0 = min(l["x0"] for l in kept)
    region_x1 = max(l["x1"] for l in kept)
    region_w = max(1.0, region_x1 - region_x0)

    # 2. Find gutters using only words from lines that are NOT contiguous
    #    full-width lines (a title crossing the gutter must not hide it).
    body_words = []
    for line in kept:
        wide = (line["x1"] - line["x0"]) > WIDE_LINE_FRACTION * region_w
        contiguous = not _central_gaps(line, region_x0, region_x1)
        if not (wide and contiguous):
            body_words.extend(line["words"])
    splits = _find_gutters(body_words, region_x0, region_x1)

    # 3. Single column: simple top-to-bottom join
    if not splits:
        return _join_lines(kept)

    # 4. Classify lines: spanning (full-width) vs columnar; group into bands
    def is_spanning(line: Dict[str, Any]) -> bool:
        if (line["x1"] - line["x0"]) <= WIDE_LINE_FRACTION * region_w:
            return False
        # A "line" of words from two columns has a whitespace gap at a gutter
        for s in splits:
            # Any single word crossing the gutter means genuinely full-width
            if any(w["x0"] < s < w["x1"] for w in line["words"]):
                return True
            left = [w for w in line["words"] if w["x1"] <= s]
            right = [w for w in line["words"] if w["x0"] >= s]
            if left and right:
                gap = min(w["x0"] for w in right) - max(w["x1"] for w in left)
                if gap >= MIN_GUTTER * 0.7:
                    return False  # actually two column lines at the same height
        return True

    bands: List[Dict[str, Any]] = []  # {spanning: bool, lines: [...]}
    for line in kept:  # kept is already in top-to-bottom order
        s = is_spanning(line)
        if bands and bands[-1]["spanning"] == s:
            bands[-1]["lines"].append(line)
        else:
            bands.append({"spanning": s, "lines": [line]})

    # 5. Assemble: spanning bands as-is; columnar bands left column first
    bounds = [region_x0 - 1] + splits + [region_x1 + 1]
    parts: List[str] = []
    for band in bands:
        if band["spanning"]:
            parts.append(_join_lines(band["lines"]))
            continue
        band_words = [w for line in band["lines"] for w in line["words"]]
        for c in range(len(bounds) - 1):
            cx0, cx1 = bounds[c], bounds[c + 1]
            col_words = [w for w in band_words if cx0 <= (w["x0"] + w["x1"]) / 2.0 < cx1]
            col_lines = _lines_from_words(col_words)
            col_text = _join_lines(col_lines)
            if col_text.strip():
                parts.append(col_text)
    return "\n\n".join(p for p in parts if p.strip())
