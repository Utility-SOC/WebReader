"""Inspection of existing PDF tag trees."""
import pytest

from backend.office import process_pdf_accessibility
from backend.pdf_tags import inspect_tags
from backend.tests.pdfgen import El, Page, build_pdf

BODY = ["The commission met on the first Tuesday of the month and", "approved the agenda after a brief discussion among", "the members who were present at the meeting."]


def _w(tmp_path, data):
    p = tmp_path / "t.pdf"; p.write_bytes(data); return str(p)


def _codes(issues):
    return [i.code for i in issues]


def _table(pg, top, alt=None, header=False):
    """A 2x2 tagged table with real cell content (pdfplumber ignores contentless elements)."""
    tbl = El("Table", alt=alt)
    rows = []
    for r in range(2):
        tr = El("TR")
        for c in range(2):
            pg.tagged_text(72 + c * 90, top + r * 16, 10, f"r{r}c{c}", tag="TH" if (header and r == 0) else "TD", parent=tr)
        tbl.children.append(tr)
    pg.elements.append(tbl)
    return tbl


def _good_page():
    pg = Page()
    pg.tagged_text(72, 60, 22, "Annual Report", tag="H1", bold=True)
    for i, ln in enumerate(BODY):
        pg.tagged_text(72, 110 + i * 14, 10, ln, tag="P")
    pg.tagged_text(72, 170, 14, "Findings", tag="H2", bold=True)
    pg.tagged_image(72, 200, 100, 60, alt="Bar chart: revenue rose each quarter")
    _table(pg, 280, alt="Budget by department")
    return pg


def test_clean_tagged_pdf_has_no_tag_issues(tmp_path):
    facts, issues = inspect_tags(_w(tmp_path, build_pdf([_good_page()], title="T", lang="en", tagged=True, display_title=True)))
    assert facts["tag_tree"] is True and facts["display_doc_title"] is True
    assert issues == []
    assert facts["tag_counts"]["Figure"] == 1 and facts["tag_counts"]["H1"] == 1


def test_untagged_pdf_has_no_tag_tree(tmp_path):
    facts, issues = inspect_tags(_w(tmp_path, build_pdf([Page().lines(72, 80, 10, BODY)])))
    assert facts["tag_tree"] is False and issues == []


def test_figure_alt_text_problems(tmp_path):
    pg = Page()
    pg.tagged_text(72, 60, 20, "Title", tag="H1", bold=True)
    pg.tagged_image(72, 100, 80, 50)                          # no alt
    pg.tagged_image(72, 170, 80, 50, alt="image1.png")        # placeholder
    pg.tagged_image(72, 240, 80, 50, alt="Image of a dog")    # redundant prefix
    pg.tagged_image(72, 310, 80, 50, alt="A dog on a porch")  # fine
    _, issues = inspect_tags(_w(tmp_path, build_pdf([pg], tagged=True)))
    assert _codes(issues) == ["FIG_ALT_MISSING", "FIG_ALT_PLACEHOLDER", "FIG_ALT_REDUNDANT"]
    assert all(i.location == "Page 1" for i in issues) and "bbox" in issues[0].detail


def test_heading_problems(tmp_path):
    pg = Page()
    pg.tagged_text(72, 60, 16, "Starts at two", tag="H2", bold=True)
    pg.tagged_text(72, 100, 12, "Then jumps", tag="H4", bold=True)
    pg.tagged_text(72, 140, 12, "Generic", tag="H", bold=True)
    _, issues = inspect_tags(_w(tmp_path, build_pdf([pg], tagged=True)))
    got = _codes(issues)
    assert "PDF_FIRST_HEADING_NOT_H1" in got and "HEADING_SKIP" in got and "PDF_GENERIC_HEADING" in got


def test_tables_follow_the_images_policy_and_structured_mode(tmp_path, monkeypatch):
    plain = Page(); plain.tagged_text(72, 60, 20, "T", tag="H1", bold=True); _table(plain, 120)
    path = _w(tmp_path, build_pdf([plain], tagged=True))
    assert _codes(inspect_tags(path)[1]) == ["TABLE_DESCRIPTION_MISSING"]
    monkeypatch.setenv("WEBREADER_TABLES", "structured")
    assert _codes(inspect_tags(path)[1]) == ["TABLE_NO_HEADER"]
    with_th = Page(); with_th.tagged_text(72, 60, 20, "T", tag="H1", bold=True); _table(with_th, 120, header=True)
    assert inspect_tags(_w(tmp_path, build_pdf([with_th], tagged=True)))[1] == []


def test_nonstandard_tags_and_role_mapping(tmp_path):
    pg = Page(); pg.tagged_text(72, 60, 20, "Custom tag", tag="MyHeading", bold=True)
    pg.tagged_text(72, 100, 10, "x", tag="P")
    unmapped = _w(tmp_path, build_pdf([pg], tagged=True))
    assert _codes(inspect_tags(unmapped)[1]) == ["PDF_NONSTANDARD_TAG"]
    pg2 = Page(); pg2.tagged_text(72, 60, 20, "Custom tag", tag="MyHeading", bold=True); pg2.tagged_text(72, 100, 10, "x", tag="P")
    facts, issues = inspect_tags(_w(tmp_path, build_pdf([pg2], tagged=True, role_map={"MyHeading": "H1"})))
    assert issues == [] and facts["tag_counts"]["H1"] == 1  # mapped, and counted as the standard type


def test_text_outside_the_tag_tree_is_flagged_but_artifacts_are_not(tmp_path):
    pg = Page()
    pg.tagged_text(72, 60, 20, "Tagged heading", tag="H1", bold=True)
    pg.lines(72, 120, 10, BODY * 3)                # plenty of untagged body text
    pg.artifact_text(72, 740, 9, "Running footer text that is decoration")
    _, issues = inspect_tags(_w(tmp_path, build_pdf([pg], tagged=True)))
    assert _codes(issues) == ["PDF_UNTAGGED_CONTENT"] and issues[0].detail["pages"] == [1]
    # same page with the body properly tagged and the footer an artifact -> clean
    ok = Page(); ok.tagged_text(72, 60, 20, "Tagged heading", tag="H1", bold=True)
    for i, ln in enumerate(BODY * 3):
        ok.tagged_text(72, 120 + i * 13, 10, ln, tag="P")
    ok.artifact_text(72, 740, 9, "Running footer text that is decoration")
    assert inspect_tags(_w(tmp_path, build_pdf([ok], tagged=True)))[1] == []


def test_display_title_issue_reported_once_for_tagged_pdfs(tmp_path):
    path = _w(tmp_path, build_pdf([_good_page()], title="Annual Report", lang="en", tagged=True))
    codes = [i["code"] for i in process_pdf_accessibility(path)["issues"]]
    assert codes == ["PDF_DISPLAY_TITLE"]
    path2 = _w(tmp_path, build_pdf([_good_page()], title="Annual Report", lang="en", tagged=True, display_title=True))
    assert process_pdf_accessibility(path2)["issues"] == []


def test_issue_listing_is_capped_but_totals_are_true(tmp_path, monkeypatch):
    import backend.pdf_tags as pt
    monkeypatch.setattr(pt, "MAX_ISSUES_PER_CODE", 3)
    pg = Page(); pg.tagged_text(72, 40, 20, "T", tag="H1", bold=True)
    for i in range(8):
        pg.tagged_image(72, 80 + i * 60, 40, 40)
    facts, issues = inspect_tags(_w(tmp_path, build_pdf([pg], tagged=True)))
    assert len([i for i in issues if i.code == "FIG_ALT_MISSING"]) == 3
    assert facts["issue_totals"]["FIG_ALT_MISSING"] == 8 and facts["issues_truncated"] == {"FIG_ALT_MISSING": 8}
