"""Characterisation tests for the smart PDF text extraction (pdf_auto), so it can be refactored safely."""
import pdfplumber
import pytest

from backend import pdf_auto
from backend.tests.pdfgen import Page, build_pdf


def _page_text(pdf_bytes, tmp_path, idx=0, repeated=None):
    p = tmp_path / "t.pdf"; p.write_bytes(pdf_bytes)
    with pdfplumber.open(str(p)) as pdf:
        return pdf_auto.extract_page_smart(pdf.pages[idx], repeated or set())


def test_single_column_paragraphs_and_dehyphenation(tmp_path):
    # Paragraph breaks are detected from the median line gap, which needs a realistic number of lines.
    pg = Page()
    pg.lines(72, 100, 11, ["This is the first para-", "graph of the document, which", "runs for three lines in all."])
    pg.lines(72, 170, 11, ["Second paragraph starts here", "and also runs for two lines."])
    pg.lines(72, 230, 11, ["Third paragraph is short."])
    out = _page_text(build_pdf([pg]), tmp_path)
    assert out == ("This is the first paragraph of the document, which runs for three lines in all.\n\n"
                   "Second paragraph starts here and also runs for two lines.\n\nThird paragraph is short.")


def test_two_columns_read_left_then_right_under_a_spanning_title(tmp_path):
    pg = Page()
    pg.text(72, 60, 18, "A Full Width Title Across Both Columns", bold=True)
    pg.lines(72, 120, 10, ["Left column line one", "left column line two", "left column line three"])
    pg.lines(330, 120, 10, ["Right column line one", "right column line two", "right column line three"])
    out = _page_text(build_pdf([pg]), tmp_path)
    assert out.index("Full Width Title") < out.index("Left column line one") < out.index("left column line three") < out.index("Right column line one")


def test_page_numbers_dropped(tmp_path):
    pg = Page()
    pg.lines(72, 100, 11, ["Body text of the page."])
    pg.text(300, 740, 10, "12")
    out = _page_text(build_pdf([pg]), tmp_path)
    assert out == "Body text of the page."


def test_repeated_header_dropped(tmp_path):
    pages = []
    for i in range(4):
        pg = Page(); pg.text(72, 30, 9, "County Planning Commission"); pg.lines(72, 100, 11, [f"Content of page {i + 1}."])
        pages.append(pg)
    p = tmp_path / "r.pdf"; p.write_bytes(build_pdf(pages))
    with pdfplumber.open(str(p)) as pdf:
        rep = pdf_auto.build_repeated_lines(pdf)
        out = pdf_auto.extract_page_smart(pdf.pages[2], rep)
    assert out == "Content of page 3."
