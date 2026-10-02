"""
OCR as a fallback for PDF text -- assuming the worst.

Real-world PDFs: scans with no text at all; scans with a *bad* OCR layer that
looks plausible but is wrong; fonts with no Unicode mapping that extract as
"(cid:123)" or private-use characters; letter-spaced garbage. So a PDF's own
text is trusted only if it passes cheap checks, and "searchable scans" are
verified by OCR-ing a few pages and comparing.

OCR returns words with positions, and pdf_auto's column / reading-order logic
works on exactly that, so an OCR page is wrapped in `OcrPage` (it quacks like a
pdfplumber page for that code) and gets the same layout handling as a text
page. Results are cached on disk by file hash, so reading, structure
analysis and verification never OCR the same page twice.
"""

import hashlib
import json
import logging
import os
import re
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import pytesseract
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger("SpeedReaderUtils")

OCR_DPI = int(os.environ.get("WEBREADER_OCR_DPI", "200"))     # 200 reads normal print fine and is ~2x faster than 300
VERIFY_DPI = 150                                                # enough to compare words when checking a text layer
OCR_LANG = os.environ.get("WEBREADER_OCR_LANG", "eng")
VERIFY_MODE = os.environ.get("WEBREADER_OCR_VERIFY", "auto").strip().lower()   # auto | always | never
VERIFY_SAMPLE_PAGES = 3          # library ingestion; interactive reading uses 1 (OCR is slow on modest hardware)
AGREEMENT_THRESHOLD = 0.6        # fewer than this fraction of embedded words confirmed by OCR = unreliable
SCANNED_IMAGE_FRACTION = 0.7     # an image this much of the page = a scan underneath
LOW_CONFIDENCE = 60.0            # mean word confidence below this: a person should look at the page
CACHE_VERSION = "v1"


# --------------------------------------------------------------------------- cache

def _cache_dir() -> str:
    d = os.environ.get("WEBREADER_CACHE_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache")
    return os.path.join(d, "ocr")


_key_memo: Dict[Tuple[str, float, int], str] = {}


def file_key(path: str) -> str:
    """Content hash of the file (memoised by path+mtime+size)."""
    st = os.stat(path)
    memo = (path, st.st_mtime, st.st_size)
    if memo not in _key_memo:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _key_memo[memo] = h.hexdigest()[:24]
    return _key_memo[memo]


def _cache_path(key: str, page_idx: int, dpi: int, lang: str) -> str:
    return os.path.join(_cache_dir(), f"{key}_{page_idx}_{dpi}_{lang}_{CACHE_VERSION}.json")


def _cache_get(key, page_idx, dpi, lang):
    try:
        with open(_cache_path(key, page_idx, dpi, lang)) as f:
            return json.load(f)
    except Exception:
        return None


def _cache_put(key, page_idx, dpi, lang, data):
    try:
        os.makedirs(_cache_dir(), exist_ok=True)
        path = _cache_path(key, page_idx, dpi, lang)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)  # atomic: a concurrent reader never sees half a file
    except Exception as e:
        logger.debug(f"OCR cache write skipped: {e}")


# --------------------------------------------------------------------------- OCR

class OcrPage:
    """Stands in for a pdfplumber page in pdf_auto's reading-order code."""

    def __init__(self, words: List[Dict[str, Any]], width: float, height: float, mean_conf: float, rotation: int = 0):
        self.words, self.width, self.height = words, width, height
        self.mean_conf, self.rotation = mean_conf, rotation

    def extract_words(self, **_kw) -> List[Dict[str, Any]]:
        return [dict(w) for w in self.words]


def _preprocess(img: Image.Image) -> Image.Image:
    """Cheap clean-up that helps poor scans: greyscale, stretch contrast."""
    g = ImageOps.grayscale(img)
    return ImageOps.autocontrast(g, cutoff=1)


def _otsu_threshold(g: Image.Image) -> int:
    hist = g.histogram()
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    best, best_t, w0, sum0 = 0.0, 128, 0, 0.0
    for t in range(256):
        w0 += hist[t]
        if w0 == 0:
            continue
        w1 = total - w0
        if w1 == 0:
            break
        sum0 += t * hist[t]
        m0, m1 = sum0 / w0, (sum_all - sum0) / w1
        var = w0 * w1 * (m0 - m1) ** 2
        if var > best:
            best, best_t = var, t
    return best_t


def _clean(img: Image.Image) -> Image.Image:
    """Second-attempt clean-up for poor scans: median-filter speckle/compression noise, then binarise."""
    g = ImageOps.grayscale(img).filter(ImageFilter.MedianFilter(5))
    t = _otsu_threshold(g)
    return g.point(lambda v: 255 if v > t else 0)


def _rotation(img: Image.Image) -> int:
    """90-degree-multiple rotation needed to make the page upright (tesseract OSD); 0 if unsure."""
    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        if float(osd.get("orientation_conf", 0)) >= 2.0:
            return int(osd.get("rotate", 0)) % 360
    except Exception:
        pass
    return 0


def _run(img: Image.Image, dpi: int, lang: str):
    data = pytesseract.image_to_data(img, lang=lang, config="--psm 3", output_type=pytesseract.Output.DICT)
    scale = 72.0 / dpi
    words: List[Dict[str, Any]] = []
    confs: List[float] = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if not text or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append({"text": text, "x0": x * scale, "x1": (x + w) * scale, "top": y * scale, "bottom": (y + h) * scale,
                      "size": h * scale, "fontname": "", "conf": conf})
        confs.append(conf)
    mean = statistics.fmean(confs) if confs else 0.0
    return words, mean, sum(confs), img.width * scale, img.height * scale


GOOD_CONFIDENCE = 70.0   # a first pass at least this confident is accepted; only poorer pages get extra attempts


def ocr_image_words(img: Image.Image, dpi: int, lang: str = OCR_LANG) -> OcrPage:
    """OCR one page image. Cheap path first: a confident first pass is accepted as is. Only a page that reads poorly
    gets the extra work (orientation detection, then a denoised/binarised retry), keeping the better result."""
    first = _preprocess(img)
    words, mean, total_conf, w, h = _run(first, dpi, lang)
    best, best_rot = (words, mean, total_conf, w, h), 0
    if mean >= GOOD_CONFIDENCE:
        return OcrPage(words, w, h, mean, 0)

    rot = _rotation(first)                       # upside-down / sideways scans read as low-confidence junk
    if rot:
        cand = _run(first.rotate(-rot, expand=True), dpi, lang)   # PIL rotates counter-clockwise; OSD's "rotate" is clockwise
        if cand[2] > best[2]:
            best, best_rot = cand, rot
    if best[1] < GOOD_CONFIDENCE:                # noise, blur, heavy compression: clean up and try again
        second = _clean(img)
        if best_rot:
            second = second.rotate(-best_rot, expand=True)
        cand = _run(second, dpi, lang)
        if cand[2] > best[2]:                    # more total confidence = more words read, more surely
            best = cand
    return OcrPage(best[0], best[3], best[4], best[1], best_rot)


def ocr_page(pdf_page, key: str, dpi: int = OCR_DPI, lang: str = OCR_LANG) -> OcrPage:
    """OCR one pdfplumber page (cached by file hash + page + dpi + language)."""
    idx = pdf_page.page_number - 1
    hit = _cache_get(key, idx, dpi, lang)
    if hit is not None:
        return OcrPage(hit["words"], hit["width"], hit["height"], hit["mean_conf"], hit.get("rotation", 0))
    img = pdf_page.to_image(resolution=dpi).original
    res = ocr_image_words(img, dpi, lang)
    _cache_put(key, idx, dpi, lang, {"words": res.words, "width": res.width, "height": res.height,
                                     "mean_conf": res.mean_conf, "rotation": res.rotation})
    return res


# --------------------------------------------------------------------------- is the text layer trustworthy?

_CID = re.compile(r"\(cid:\d+\)")


_LEADERS = re.compile(r"[._\-=*~\u2014\u2013\u2026|/\\]{3,}")   # "______" signature lines, dotted leaders, rules

# Signals that are certain enough to OCR on sight, vs. ones that are only suspicious. A wrong "OCR it" costs
# minutes per page on modest hardware, so suspicious pages are verified (see plan_ocr) instead of being OCR'd blindly.
STRONG_REASONS = {"no_text", "unmapped_glyphs", "garbage_characters"}


def page_text(page) -> str:
    """A page's text WITH word spacing. (Joining pdfplumber's characters directly glues words together on the many
    PDFs that position words instead of storing space characters -- which once made nearly every page look 'garbled'.)"""
    from .pdf_auto import replace_nonchars
    try:
        return replace_nonchars(page.extract_text(x_tolerance=1.5, y_tolerance=3) or "")
    except Exception:
        return ""


def text_layer_quality(text: str) -> Tuple[bool, List[str]]:
    """Cheap checks for a page's embedded text (which must already have word spacing -- see page_text).
    Returns (looks_ok, reasons it doesn't). Reasons in STRONG_REASONS are certain; the rest are only suspicious."""
    chars = [c for c in text if not c.isspace()]
    n = len(chars)
    if n == 0:
        return False, ["no_text"]
    reasons: List[str] = []
    cid_chars = sum(len(m) for m in _CID.findall(text))
    if cid_chars / max(1, len(text)) > 0.02:
        reasons.append("unmapped_glyphs")
    bad = sum(1 for c in chars if c == "\ufffd" or "\ue000" <= c <= "\uf8ff" or (ord(c) < 32))
    if bad / n > 0.03:
        reasons.append("garbage_characters")
    if n >= 80:
        stripped = _LEADERS.sub(" ", text)            # blanks and leaders are normal in forms and leases
        sc = [c for c in stripped if not c.isspace()]
        if len(sc) >= 80 and sum(1 for c in sc if c.isalnum()) / len(sc) < 0.4:
            reasons.append("mostly_symbols")
        words = stripped.split()
        if words:
            if sum(1 for w in words if len(w) > 30) / len(words) > 0.15:
                reasons.append("spacing_lost")
            if len(words) >= 20 and sum(1 for w in words if len(w) == 1 and w.isalpha()) / len(words) > 0.4:
                reasons.append("letter_spaced")
    return (not reasons), reasons


def is_scanned_page(page) -> bool:
    area = float(page.width) * float(page.height) or 1.0
    return any(((im["x1"] - im["x0"]) * (im["bottom"] - im["top"])) >= SCANNED_IMAGE_FRACTION * area for im in page.images)


def _tokens(text: str) -> Set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower())}


def agreement(embedded_text: str, ocr_text: str) -> Optional[float]:
    """Fraction of the embedded text's words that OCR of the same page also found (None if too little to compare)."""
    e, o = _tokens(embedded_text), _tokens(ocr_text)
    if len(e) < 8:
        # Lots of embedded text but almost no recognisable words in it (spaces lost, glued together) while OCR of the
        # same page finds plenty: the text layer is unusable, which is a clear answer, not "too little to compare".
        if len(embedded_text.strip()) >= 80 and len(o) >= 8:
            return 0.0
        return None
    return len(e & o) / len(e)


@dataclass
class OcrPlan:
    ocr_pages: Set[int] = field(default_factory=set)                 # 0-based page indexes that must be OCR'd
    reasons: Dict[int, str] = field(default_factory=dict)
    agreement: List[float] = field(default_factory=list)             # sampled embedded-vs-OCR agreement
    unreliable_layer: bool = False                                    # searchable scan whose text doesn't match the image
    scanned_with_text: List[int] = field(default_factory=list)
    suspect_pages: List[int] = field(default_factory=list)           # looked odd, but OCR showed the text layer is fine


def _spread(items: List[int], n: int) -> List[int]:
    if len(items) <= n:
        return list(items)
    if n <= 1:
        return [items[len(items) // 2]]      # one sample: take the middle of the document, not the cover page
    step = (len(items) - 1) / (n - 1)
    return [items[round(i * step)] for i in range(n)]


def plan_ocr(pdf, key: str, max_pages: int = 400, verify: str = VERIFY_MODE, pages: Optional[List[int]] = None,
             sample_pages: int = VERIFY_SAMPLE_PAGES) -> OcrPlan:
    """Decide which pages need OCR, assuming nothing about the PDF's own text -- but without OCR-ing on a hunch.

    Certain signals (no text layer on a page with content, unmapped glyphs, garbage characters) mean OCR. Merely
    suspicious pages, and "searchable scans" (a page image with a text layer on top), are checked by OCR-ing a few
    sampled pages at low resolution and comparing words: only if the text layer disagrees with the image are all of
    them re-OCR'd. OCR is slow on modest hardware, so a wrong guess has to be expensive to make, not cheap.

    pages: 0-based page indexes to plan for (default: the first max_pages).
    """
    plan = OcrPlan()
    texts: Dict[int, str] = {}
    suspects: List[int] = []
    indexes = pages if pages is not None else list(range(min(len(pdf.pages), max_pages)))
    for i in indexes:
        page = pdf.pages[i]
        text = page_text(page)
        texts[i] = text
        if not text.strip():
            # A blank page is not a scan: only OCR if there's something on it to read.
            if page.images or len(page.curves) + len(page.lines) + len(page.rects) > 20:
                plan.ocr_pages.add(i); plan.reasons[i] = "no_text"
            continue
        ok, why = text_layer_quality(text)
        if not ok and STRONG_REASONS & set(why):
            plan.ocr_pages.add(i); plan.reasons[i] = "garbled:" + ",".join(why)
        elif not ok:
            suspects.append(i); plan.reasons[i] = "suspicious:" + ",".join(why)
        elif is_scanned_page(page):
            plan.scanned_with_text.append(i)

    to_check = sorted(set(suspects) | set(plan.scanned_with_text))
    plan.suspect_pages = suspects
    if verify != "never" and to_check:
        for i in _spread(to_check, max(1, sample_pages)):
            a = agreement(texts[i], page_text_from_ocr(ocr_page(pdf.pages[i], key, dpi=VERIFY_DPI)))
            if a is not None:
                plan.agreement.append(a)
        if plan.agreement and statistics.median(plan.agreement) < AGREEMENT_THRESHOLD:
            plan.unreliable_layer = True
            for i in to_check:
                plan.ocr_pages.add(i); plan.reasons[i] = "unreliable_text_layer"
    # Suspects that were not shown to be bad (or couldn't be checked) are trusted: their text layer is used as is.
    for i in suspects:
        if i not in plan.ocr_pages:
            plan.reasons.pop(i, None)
    return plan


# --------------------------------------------------------------------------- text from OCR

def page_text_from_ocr(ocr: OcrPage, repeated: Optional[Set[str]] = None) -> str:
    """Reading-order text for an OCR'd page, using the same column / paragraph logic as text pages."""
    from .pdf_auto import _join_lines, reading_order_groups
    parts = [_join_lines(g) for g in reading_order_groups(ocr, repeated or set())]
    return "\n\n".join(p for p in parts if p.strip())
