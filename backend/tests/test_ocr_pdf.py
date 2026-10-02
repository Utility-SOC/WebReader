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
    ("T h e c o u n c i l m e t o n T u e s d a y a n d a p p r o v e d t h e a g e n d a " * 3, False),
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


# ------------------------------------------------------------ regression: a normal PDF must never be sent to OCR
# (A real 20-page lease was OCR'd page by page for ~40 minutes because words positioned without space characters
#  looked "garbled" when characters were joined directly.)

SENTENCES = ["This lease is made between the landlord and the tenant named below.", "The tenant agrees to pay rent on the first day of each month.",
             "The premises shall be used only as a private dwelling and for no other purpose.", "Pets are not permitted without prior written consent of the landlord."]


def _no_space_pdf(tmp_path, pages=12):
    pgs = []
    for _ in range(pages):
        pg = Page()
        for i, ln in enumerate(SENTENCES * 2):
            pg.words(72, 100 + i * 16, 11, ln.split())
        pgs.append(pg)
    return write(tmp_path, pgs)


class _Boom:
    calls = 0

    def __call__(self, *a, **k):
        _Boom.calls += 1
        raise AssertionError("OCR was called for a PDF with a perfectly good text layer")


def test_pdf_without_space_characters_is_read_not_ocrd(tmp_path, monkeypatch):
    path = _no_space_pdf(tmp_path)
    monkeypatch.setattr(ocr_pdf.pytesseract, "image_to_data", _Boom())
    monkeypatch.setattr(ocr_pdf.pytesseract, "image_to_osd", _Boom())
    import backend.utils as u
    monkeypatch.setattr(u.pytesseract, "image_to_string", _Boom())
    with pdfplumber.open(path) as pdf:
        plan = ocr_pdf.plan_ocr(pdf, ocr_pdf.file_key(path))
    assert plan.ocr_pages == set() and plan.suspect_pages == []
    text, _ = extract_text_from_pdf_range(path, 1)
    assert "landlord and the tenant" in text and _Boom.calls == 0


def test_page_text_has_word_spacing_even_when_the_pdf_has_no_space_characters(tmp_path):
    path = _no_space_pdf(tmp_path, pages=1)
    with pdfplumber.open(path) as pdf:
        raw = "".join(c["text"] for c in pdf.pages[0].chars)
        spaced = ocr_pdf.page_text(pdf.pages[0])
    assert " " not in raw.strip().split("\n")[0] and "landlordandthetenant" in raw.replace(" ", "")   # why the old check misfired
    assert "landlord and the tenant" in spaced and ocr_pdf.text_layer_quality(spaced)[0]


def test_forms_full_of_blank_lines_are_not_mostly_symbols():
    text = ("Tenant signature: ______________________________ Date: ____________________\n" * 6 +
            "Landlord signature: .................................. Date: ..................\n" * 4 +
            "Witness: ------------------------------------------------\n" * 3 + "Page footer text for this form document here.")
    assert ocr_pdf.text_layer_quality(text) == (True, [])


def test_a_suspicious_page_is_verified_not_blindly_ocrd(tmp_path, monkeypatch):
    # The text layer matches the image, but pretend a heuristic found it suspicious: one cheap check clears it.
    good = " ".join(LEFT + RIGHT)
    path = write(tmp_path, [Page().scan(scan_image(LEFT, RIGHT)).text(72, 100, 10, good, invisible=True)])
    real = ocr_pdf.text_layer_quality
    monkeypatch.setattr(ocr_pdf, "text_layer_quality", lambda t: (False, ["spacing_lost"]))
    with pdfplumber.open(path) as pdf:
        plan = ocr_pdf.plan_ocr(pdf, ocr_pdf.file_key(path), sample_pages=1)
    assert plan.ocr_pages == set() and plan.suspect_pages == [0] and plan.agreement and plan.agreement[0] > 0.8
    assert plan.reasons == {}          # cleared: nothing left marked suspicious
    monkeypatch.setattr(ocr_pdf, "text_layer_quality", real)


def test_a_suspicious_page_whose_text_layer_disagrees_with_the_image_is_ocrd(tmp_path):
    run_together = "".join(" ".join(LEFT + RIGHT).lower().split())     # every space gone, as in a bad export
    pg = Page().scan(scan_image(LEFT, RIGHT)).text(36, 100, 4, run_together, invisible=True)   # small enough to stay on the page
    path = write(tmp_path, [pg])
    with pdfplumber.open(path) as pdf:
        plan = ocr_pdf.plan_ocr(pdf, ocr_pdf.file_key(path), sample_pages=1)
    assert 0 in plan.ocr_pages and plan.unreliable_layer


def test_only_the_requested_pages_are_planned(tmp_path, monkeypatch):
    path = _no_space_pdf(tmp_path, pages=8)
    seen = {}
    real = ocr_pdf.plan_ocr
    monkeypatch.setattr(ocr_pdf, "plan_ocr", lambda pdf, key, **kw: seen.update(kw) or real(pdf, key, **kw))
    extract_text_from_pdf_range(path, 3, 5)
    assert seen["pages"] == [2, 3, 4]


def test_a_confident_first_pass_skips_the_expensive_extras(monkeypatch):
    monkeypatch.setattr(ocr_pdf, "_rotation", _Boom())
    monkeypatch.setattr(ocr_pdf, "_clean", _Boom())
    page = ocr_pdf.ocr_image_words(scan_image(LEFT, RIGHT), 300)
    assert page.mean_conf >= ocr_pdf.GOOD_CONFIDENCE and page.rotation == 0


def test_spread_samples_evenly_including_a_single_sample():
    assert ocr_pdf._spread([1, 2, 3, 4, 5, 6, 7], 1) == [4]
    assert ocr_pdf._spread([1, 2, 3, 4, 5, 6, 7], 3) == [1, 4, 7]
    assert ocr_pdf._spread([2, 9], 3) == [2, 9] and ocr_pdf._spread([], 1) == []


# ------------------------------------------------------------ regression: space glyph mapped to a Unicode non-character
# (A real lease did this: every word separator was U+FFFF, so each line was one 90-character "word" -- the text was fine,
#  which OCR confirmed, but the reader would have flashed whole lines.)

LINE = "The\uffffTenant\uffffagrees\uffffto\uffffpay\uffffrent\uffffon\uffffthe\uffff1st\uffffof\uffffeach\uffffmonth."


def test_replace_nonchars_only_touches_noncharacters():
    from backend.pdf_auto import clean_text, replace_nonchars
    assert replace_nonchars("a\uffffb\ufffec\ufdd0d") == "a b c d"
    assert replace_nonchars("caf\u00e9 \u00a0 ok\ufffd") == "caf\u00e9 \u00a0 ok\ufffd"     # ordinary text, nbsp and U+FFFD are left alone
    assert clean_text("  a\uffff\uffffb   c ") == "a b c"


def test_lines_and_paragraph_text_are_spaced_when_words_contain_nonchars():
    from backend.pdf_auto import _lines_from_words
    w = {"text": LINE, "x0": 72.0, "x1": 480.0, "top": 100.0, "bottom": 111.0}
    line = _lines_from_words([w])[0]
    assert line["text"] == "The Tenant agrees to pay rent on the 1st of each month."


def test_ocr_text_path_and_page_text_normalise_too():
    words = [{"text": LINE, "x0": 72.0, "x1": 480.0, "top": 100.0, "bottom": 111.0, "size": 11, "fontname": "", "conf": 90}]
    out = ocr_pdf.page_text_from_ocr(ocr_pdf.OcrPage(words, 612, 792, 90))
    assert out == "The Tenant agrees to pay rent on the 1st of each month."

    class FakePage:
        def extract_text(self, **kw):
            return (LINE + "\n") * 12
    t = ocr_pdf.page_text(FakePage())
    assert "\uffff" not in t and ocr_pdf.text_layer_quality(t) == (True, [])      # and it no longer looks "garbled"
