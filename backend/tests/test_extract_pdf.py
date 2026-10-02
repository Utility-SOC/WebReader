"""PDF structure inference on generated PDFs."""
import pytest

from backend.extract_pdf import extract_pdf_structure
from backend.office import process_pdf_accessibility
from backend.tests.pdfgen import Page, build_pdf

BODY = ["The commission met on the first Tuesday of the month and", "approved the agenda after a brief discussion among", "the members who were present at the meeting."]


def _write(tmp_path, pdf_bytes, name="t.pdf"):
    p = tmp_path / name; p.write_bytes(pdf_bytes); return str(p)


def _doc_page():
    pg = Page()
    pg.text(72, 60, 22, "Annual Report", bold=True)
    pg.text(72, 110, 15, "Public Comment", bold=True)
    pg.lines(72, 140, 10, BODY)
    pg.lines(72, 200, 10, ["Residents raised these concerns:"])
    pg.lines(72, 216, 10, ["- traffic near the school", "- noise after midnight", "- parking limits"])
    pg.text(72, 290, 12, "Next Steps", bold=True)
    pg.lines(72, 315, 10, BODY)
    return pg


def test_headings_levels_paragraphs_and_lists(tmp_path):
    s = extract_pdf_structure(_write(tmp_path, build_pdf([_doc_page()])))
    got = [(b.kind, b.level, b.text) for b in s.blocks]
    assert got[0] == ("heading", 1, "Annual Report")
    assert ("heading", 2, "Public Comment") in got
    assert ("heading", 3, "Next Steps") in got
    items = [b.text for b in s.blocks if b.kind == "list_item"]
    assert items == ["traffic near the school", "noise after midnight", "parking limits"]
    paras = [b for b in s.blocks if b.kind == "paragraph"]
    assert paras[0].text.startswith("The commission met") and all(b.extra["inferred"] for b in s.blocks)


def test_figure_and_ruled_table_are_blocks_in_order_and_table_text_is_not_duplicated(tmp_path):
    pg = Page()
    pg.lines(72, 80, 10, BODY)
    pg.image(72, 150, 120, 80)
    pg.grid(72, 260, 100, 24, cols=2, rows=3)
    for r, row in enumerate([["Item", "Cost"], ["Roads", "1200"], ["Parks", "800"]]):
        for c, cell in enumerate(row):
            pg.text(78 + c * 100, 266 + r * 24, 10, cell)
    pg.lines(72, 400, 10, ["Closing paragraph after the table and figure that", "finishes the document nicely for the test."])
    s = extract_pdf_structure(_write(tmp_path, build_pdf([pg])))
    kinds = [b.kind for b in s.blocks]
    assert kinds == ["paragraph", "figure", "table", "paragraph"]
    tbl = s.tables()[0]
    assert tbl.rows == [["Item", "Cost"], ["Roads", "1200"], ["Parks", "800"]]
    assert not any("Roads" in b.text for b in s.blocks if b.kind == "paragraph")


def test_scanned_page_is_not_a_figure(tmp_path):
    pg = Page().image(0, 0, 612, 792)  # a full-page image and no text
    s = extract_pdf_structure(_write(tmp_path, build_pdf([pg])))
    assert s.figures() == [] and s.metadata["image_only_pages"] == [1]


def test_tiny_images_ignored(tmp_path):
    pg = Page().lines(72, 80, 10, BODY).image(72, 200, 8, 8)
    assert extract_pdf_structure(_write(tmp_path, build_pdf([pg]))).figures() == []


def test_body_size_headings_by_bold_only(tmp_path):
    pg = Page()
    pg.lines(72, 80, 10, BODY)
    pg.text(72, 140, 10, "A Bold Run In Label", bold=True)
    pg.lines(72, 160, 10, BODY)
    s = extract_pdf_structure(_write(tmp_path, build_pdf([pg])))
    assert [b.text for b in s.headings()] == ["A Bold Run In Label"]


def test_metadata_title_lang_and_tagged_flag(tmp_path):
    s = extract_pdf_structure(_write(tmp_path, build_pdf([_doc_page()], title="Annual Report 2026", lang="en-US", tagged=True)))
    assert s.title == "Annual Report 2026" and s.language == "en-US" and s.metadata["tagged"] is True


def test_pdf_accessibility_issues_untagged(tmp_path):
    pg = Page().lines(72, 80, 10, BODY).image(72, 150, 120, 80)
    pg.grid(72, 260, 100, 24, cols=2, rows=2)
    pg.text(78, 266, 10, "A"); pg.text(178, 266, 10, "B"); pg.text(78, 290, 10, "C"); pg.text(178, 290, 10, "D")
    acc = process_pdf_accessibility(_write(tmp_path, build_pdf([pg])))
    codes = {i["code"] for i in acc["issues"]}
    assert {"PDF_UNTAGGED", "PDF_LANGUAGE_MISSING", "PDF_TITLE_MISSING", "FIG_ALT_MISSING", "TABLE_DESCRIPTION_MISSING"} <= codes
    assert "DOC_TITLE_MISSING" not in codes  # PDFs report title/language once, via the PDF-specific checks
    assert acc["structure"]["format"] == "pdf"


def test_pdf_tagged_is_not_falsely_flagged(tmp_path):
    pg = Page().lines(72, 80, 10, BODY).image(72, 150, 120, 80)
    acc = process_pdf_accessibility(_write(tmp_path, build_pdf([pg], title="T", lang="en", tagged=True)))
    codes = {i["code"] for i in acc["issues"]}
    assert "PDF_UNTAGGED" not in codes and "FIG_ALT_MISSING" not in codes and "PDF_TAG_TREE_NOT_INSPECTED" in codes
