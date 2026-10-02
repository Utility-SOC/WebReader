"""OCR fallback for PDF text: assume the PDF's own text can't be trusted."""
import os

import pdfplumber
import pytest
from PIL import Image, ImageDraw, ImageFont

from backend import ocr_pdf
from backend.extract_pdf import extract_pdf_structure
from backend.office import process_pdf_accessibility
from backend.tests.pdfgen import Page, build_pdf
from backend.utils import extract_text_from_pdf_range

W, H = 2550, 3300  # a US-letter page at 300 dpi
LEFT = ["Council approved the annual budget", "after a long discussion about roads", "and the new community library plan"]
RIGHT = ["Residents asked for better lighting", "near the school crossing and parks", "before the winter season begins"]


def scan_image(lines_left, lines_right=None, size=44, top=400, heading=None, rotate=0):
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=size)
    if heading:
        d.text((300, 150), heading, font=ImageFont.load_default(size=int(size * 1.9)), fill=0)
    for i, ln in enumerate(lines_left):
        d.text((300, top + i * size * 2), ln, font=font, fill=0)
    for i, ln in enumerate(lines_right or []):
        d.text((1400, top + i * size * 2), ln, font=font, fill=0)
    return im.rotate(rotate, expand=False) if rotate else im


def write(tmp_path, pages, **kw):
    p = tmp_path / "t.pdf"; p.write_bytes(build_pdf(pages, **kw)); return str(p)


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBREADER_CACHE_DIR", str(tmp_path / "cache"))


# ------------------------------------------------------------ text-layer quality (pure functions)

@pytest.mark.parametrize("text,ok", [
    ("The council met on Tuesday and approved the agenda after a brief discussion among the members.", True),
    ("(cid:12)(cid:45)(cid:7)(cid:99) some text that is otherwise fine (cid:3)(cid:4)(cid:5)(cid:6)", False),
    ("  normal words here ", False),
    ("T h e c o u n c i l m e t o n T u e s d a y a n d a p p r o v e d t h e a g e n d a", False),
    ("Thecouncilmetonthefirsttuesdayandapprovedtheagendaafterabriefdiscussionamongthememberswhoweregathered", False),
    ("", False),
])
def test_text_layer_quality(text, ok):
    assert ocr_pdf.text_layer_quality(text)[0] is ok


def test_agreement():
    assert ocr_pdf.agreement("council approved the annual budget after discussion about roads library plan", "Council approved the annual budget after discussion about roads and library plan") > 0.9
    assert ocr_pdf.agreement("council approved the annual budget after discussion about roads library plan", "zebra quartz mango violin") < 0.2
    assert ocr_pdf.agreement("too few", "words") is None


# ------------------------------------------------------------ scans

def test_pure_scan_is_ocrd_in_column_order(tmp_path):
    path = write(tmp_path, [Page().scan(scan_image(LEFT, RIGHT))])
    text, _ = extract_text_from_pdf_range(path, 1)
    low = text.lower()
    assert "annual budget" in low and "winter season" in low
    assert low.index("annual budget") < low.index("community library") < low.index("better lighting") < low.index("winter season")


def test_ocr_result_is_cached(tmp_path, monkeypatch):
    path = write(tmp_path, [Page().scan(scan_image(LEFT))])
    key = ocr_pdf.file_key(path)
    with pdfplumber.open(path) as pdf:
        first = ocr_pdf.ocr_page(pdf.pages[0], key)
        monkeypatch.setattr(ocr_pdf.pytesseract, "image_to_data", lambda *a, **k: (_ for _ in ()).throw(AssertionError("OCR ran again")))
        monkeypatch.setattr(ocr_pdf.pytesseract, "image_to_osd", lambda *a, **k: (_ for _ in ()).throw(AssertionError("OCR ran again")))
        second = ocr_pdf.ocr_page(pdf.pages[0], key)
    assert [w["text"] for w in second.words] == [w["text"] for w in first.words] and first.mean_conf > 60


def test_rotated_scan_is_straightened(tmp_path):
    path = write(tmp_path, [Page().scan(scan_image(LEFT, RIGHT, rotate=180))])
    text, _ = extract_text_from_pdf_range(path, 1)
    assert "annual budget" in text.lower() and "winter season" in text.lower()


def test_blank_page_is_not_ocrd(tmp_path):
    path = write(tmp_path, [Page().lines(72, 80, 11, ["Some real text on page one of this document that is long enough."]), Page()])
    with pdfplumber.open(path) as pdf:
        plan = ocr_pdf.plan_ocr(pdf, ocr_pdf.file_key(path))
    assert plan.ocr_pages == set()


# ------------------------------------------------------------ text layers that lie

def test_searchable_scan_with_wrong_text_layer_is_detected_and_ocrd(tmp_path):
    bogus = "zebra quartz mango violin harbor pencil jungle orange castle window silver garden"
    pg = Page().scan(scan_image(LEFT, RIGHT)).text(72, 100, 10, bogus, invisible=True)
    path = write(tmp_path, [pg])
    with pdfplumber.open(path) as pdf:
        plan = ocr_pdf.plan_ocr(pdf, ocr_pdf.file_key(path))
    assert plan.unreliable_layer and plan.reasons[0] == "unreliable_text_layer" and plan.agreement[0] < 0.3
    text, _ = extract_text_from_pdf_range(path, 1)
    assert "zebra" not in text.lower() and "annual budget" in text.lower()


def test_searchable_scan_with_matching_text_layer_is_trusted(tmp_path):
    good = " ".join(LEFT + RIGHT)
    pg = Page().scan(scan_image(LEFT, RIGHT)).text(72, 100, 10, good, invisible=True)
    path = write(tmp_path, [pg])
    with pdfplumber.open(path) as pdf:
        plan = ocr_pdf.plan_ocr(pdf, ocr_pdf.file_key(path))
    assert not plan.unreliable_layer and plan.ocr_pages == set() and plan.agreement and plan.agreement[0] > 0.8


def test_garbled_text_layer_triggers_ocr(tmp_path):
    garbage = "(cid:12)(cid:45)(cid:7)(cid:99)(cid:3) (cid:4)(cid:5)(cid:6)(cid:8) (cid:9)(cid:10)(cid:11) (cid:13)(cid:14)(cid:15)(cid:16)"
    pg = Page().scan(scan_image(LEFT, RIGHT)).text(72, 100, 10, garbage, invisible=True)
    path = write(tmp_path, [pg])
    with pdfplumber.open(path) as pdf:
        plan = ocr_pdf.plan_ocr(pdf, ocr_pdf.file_key(path))
    assert plan.reasons[0].startswith("garbled") and 0 in plan.ocr_pages


def test_verification_can_be_switched_off(tmp_path):
    bogus = "zebra quartz mango violin harbor pencil jungle orange castle window silver garden"
    path = write(tmp_path, [Page().scan(scan_image(LEFT, RIGHT)).text(72, 100, 10, bogus, invisible=True)])
    with pdfplumber.open(path) as pdf:
        plan = ocr_pdf.plan_ocr(pdf, ocr_pdf.file_key(path), verify="never")
    assert plan.ocr_pages == set() and plan.agreement == []


# ------------------------------------------------------------ structure + issues on OCR'd pages

def test_structure_from_ocr_finds_the_heading(tmp_path):
    path = write(tmp_path, [Page().scan(scan_image(LEFT + LEFT, None, heading="Budget Hearing"))])
    s = extract_pdf_structure(path)
    assert s.metadata["ocr_pages"] == [1] and s.metadata["ocr_confidence"]["1"] > 60
    assert [(h.level, h.text) for h in s.headings()] == [(1, "Budget Hearing")]
    assert any("annual budget" in b.text.lower() for b in s.blocks if b.kind == "paragraph")


def test_accessibility_issues_for_a_bad_scan(tmp_path):
    bogus = "zebra quartz mango violin harbor pencil jungle orange castle window silver garden"
    codes = lambda p: {i["code"] for i in process_pdf_accessibility(p)["issues"]}
    liar = write(tmp_path, [Page().scan(scan_image(LEFT, RIGHT)).text(72, 100, 10, bogus, invisible=True)])
    assert "PDF_TEXT_LAYER_UNRELIABLE" in codes(liar)
    pure = tmp_path / "pure"; pure.mkdir()
    only = write(pure, [Page().scan(scan_image(LEFT, RIGHT))])
    assert "PDF_NO_TEXT" in codes(only) and "PDF_TEXT_LAYER_UNRELIABLE" not in codes(only)
    mixed = tmp_path / "mixed"; mixed.mkdir()
    both = write(mixed, [Page().lines(72, 80, 11, ["Real text on the first page of the mixed document, long enough to count."]), Page().scan(scan_image(LEFT))])
    assert "PDF_PAGES_WITHOUT_TEXT" in codes(both)


# ------------------------------------------------------------ bad scans (measured on degraded copies)

def _words(page):
    import re
    return set(re.findall(r"[a-z]{3,}", " ".join(w["text"] for w in page.words).lower()))


def test_heavily_compressed_scan_gets_a_cleaned_up_second_attempt():
    import io
    b = io.BytesIO(); scan_image(LEFT, RIGHT).save(b, "JPEG", quality=10); b.seek(0)
    page = ocr_pdf.ocr_image_words(Image.open(b).convert("L"), 300)
    truth = {"council", "approved", "annual", "budget", "residents", "asked", "better", "lighting", "winter", "season"}
    assert len(truth & _words(page)) >= 9 and page.mean_conf > 75   # was 0 words before the retry existed


def test_speckled_scan_is_cleaned_up():
    import random
    im = scan_image(LEFT, RIGHT); px = im.load(); random.seed(1)
    for _ in range(int(W * H * 0.05)):
        px[random.randrange(W), random.randrange(H)] = random.choice((0, 255))
    page = ocr_pdf.ocr_image_words(im, 300)
    assert {"council", "budget", "lighting", "winter"} <= _words(page)


def test_unreadable_page_is_flagged_not_silently_passed(tmp_path):
    from PIL import ImageFilter
    blurred = scan_image(LEFT + LEFT, RIGHT).filter(ImageFilter.GaussianBlur(7))  # beyond what OCR can recover
    path = write(tmp_path, [Page().scan(blurred)])
    acc = process_pdf_accessibility(path)
    assert "OCR_LOW_CONFIDENCE" in {i["code"] for i in acc["issues"]} or "PDF_NO_TEXT" in {i["code"] for i in acc["issues"]}
