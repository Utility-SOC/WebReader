"""Admin accessibility report: aggregation, guidance coverage, HTML/CSV safety."""
import csv
import io
import json
import re
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")
pptx = pytest.importorskip("pptx")

from backend import ingest, report
from backend.library_models import Item, ItemDerivative, Source
from backend.report_guidance import GUIDANCE, WCAG_NAMES, describe
from backend.tests.test_library import _docx, _pdf, _pptx, db, make_source, repo  # noqa: F401  (fixtures)


@pytest.fixture
def synced(db, repo):
    src = make_source(db, repo, include=["public/**", "private/**"], exclude=[], hold_new=True)
    (repo / "public" / "broken.docx").write_bytes(b"not a zip file")
    ingest.sync_source(db, src)
    ingest.release(db, src, ["public/budget.pptx"])
    return db


# ------------------------------------------------------------------ guidance catalogue stays complete

def test_every_issue_code_has_plain_language_guidance():
    root = Path(__file__).resolve().parents[1]
    codes = set()
    for name in ("a11y_checks.py", "pdf_tags.py", "office.py"):
        codes |= set(re.findall(r'Issue\("([A-Z0-9_]+)"', (root / name).read_text()))
    assert len(codes) >= 30
    missing = sorted(c for c in codes if c not in GUIDANCE)
    assert not missing, f"issue types without guidance in report_guidance.py: {missing}"
    for code, (title, why, how) in GUIDANCE.items():
        assert title and why and how, code
    assert describe("SOMETHING_NEW")["title"] == "Something new"      # unknown codes degrade gracefully


def test_every_wcag_criterion_used_by_the_checks_is_named():
    root = Path(__file__).resolve().parents[1]
    used = set()
    for name in ("a11y_checks.py", "pdf_tags.py"):
        used |= set(re.findall(r'"(\d\.\d\.\d)"', (root / name).read_text()))
    assert used and used <= set(WCAG_NAMES), used - set(WCAG_NAMES)


# ------------------------------------------------------------------ aggregation

def test_report_totals_and_ordering(synced):
    r = report.build_report(synced)
    o = r["overview"]
    assert o["documents"] == o["ready"] + o["failed"] + o["unsupported"] + o["removed"] and o["failed"] == 1
    assert o["released"] == 1 and o["held"] == o["ready"] - 1
    assert o["issues"] == o["errors"] + o["warnings"] + o["notices"] and o["issues"] > 0
    assert sum(r["by_fix"].values()) == o["issues"]
    sev = [c["severity"] for c in r["by_code"]]
    assert sev == sorted(sev, key={"error": 0, "warning": 1, "info": 2}.get)           # errors first
    docs = {d["id"]: d for d in r["documents"]}
    errs = [docs[i]["errors"] for i in r["attention"]]
    assert errs == sorted(errs, reverse=True)                                           # worst documents first
    assert [p["path"] for p in r["problems"]] == ["public/broken.docx"] and r["problems"][0]["error"]
    assert any(c["code"] == "DOC_TITLE_MISSING" and c["documents"] >= 1 for c in r["by_code"])


def test_a_clean_document_counts_as_clean(synced):
    r = report.build_report(synced)
    minutes = next(d for d in r["documents"] if d["path"] == "public/planning/minutes.docx")
    assert minutes["analysed"] and minutes["issue_total"] == 0 and r["overview"]["clean"] >= 1


def test_truncated_issue_lists_report_the_true_totals(db, repo):
    src = make_source(db, repo)
    ingest.sync_source(db, src)
    it = db.query(Item).filter(Item.path == "public/notice.pdf").one()
    row = db.query(ItemDerivative).filter(ItemDerivative.item_id == it.id, ItemDerivative.kind == "accessibility").one()
    data = dict(row.data)
    data["issues"] = [{"code": "FIG_ALT_MISSING", "severity": "error", "message": "m", "location": "Page 1", "wcag": "1.1.1", "fix": "suggest", "detail": {}}] * 3
    data["summary"] = {"total": 3, "truncated": {"FIG_ALT_MISSING": 6809}}
    row.data = data
    db.commit()
    r = report.build_report(db)
    c = next(c for c in r["by_code"] if c["code"] == "FIG_ALT_MISSING")
    assert c["occurrences"] == 6809 and c["documents"] == 1


def test_unknown_source_is_an_error(db):
    with pytest.raises(ValueError):
        report.build_report(db, "nope")


def test_empty_library_reports_cleanly(db):
    r = report.build_report(db)
    assert r["overview"]["documents"] == 0
    assert "No issues were found" in report.render_html(r) and "Documents: 0" in report.render_text(r)


# ------------------------------------------------------------------ renderers

def test_text_summary_is_honest(synced):
    t = report.render_text(report.build_report(synced))
    assert "Could not be processed" in t and "not a compliance claim" in t and "public/broken.docx" in t


def test_html_is_self_contained_and_structured(synced):
    h = report.render_html(report.build_report(synced))
    assert h.startswith("<!doctype html><html lang=\"en\">") and "<title>Accessibility report" in h
    assert "<script" not in h and "http://" not in h and "https://" not in h and "src=" not in h        # no scripts, nothing loaded from anywhere
    assert "Content-Security-Policy" in h and "default-src 'none'" in h
    assert h.count("<h1") == 1 and 'href="#main"' in h and h.count("<caption>") >= 4
    assert 'scope="col"' in h and 'scope="row"' in h and "prefers-color-scheme:dark" in h
    assert "Internal document" in h and "not a statement of compliance" in h
    assert re.search(r'<span class="sev error"><span aria-hidden="true">.</span> Error</span>', h)        # severity in words, not only colour
    ids = set(re.findall(r'id="(doc-\d+)"', h))
    assert ids and all(f'href="#{i}"' in h for i in ids)                                                  # every detail section is linked


def test_html_escapes_everything_from_the_repository(db, repo):
    _docx(repo / "public" / "evil.docx", title='<script>alert(1)</script> & "quotes"', head=None)
    src = make_source(db, repo, hold_new=False)
    ingest.sync_source(db, src)
    it = db.query(Item).filter(Item.path == "public/evil.docx").one()
    it.title = '<img src=x onerror=alert(1)>'
    db.commit()
    h = report.render_html(report.build_report(db))
    assert "<img src=x" not in h and "&lt;img src=x onerror=alert(1)&gt;" in h
    assert "<script>alert" not in h


def test_csv_has_one_row_per_issue_and_blocks_formula_injection(db, repo):
    src = make_source(db, repo, hold_new=False)
    ingest.sync_source(db, src)
    it = db.query(Item).filter(Item.path == "public/budget.pptx").one()
    it.title = '=HYPERLINK("http://evil","click")'
    db.commit()
    text = report.render_csv(report.build_report(db))
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows and {"source", "path", "title", "severity", "problem", "code", "wcag", "fix"} <= set(rows[0])
    assert all(not any(v.startswith(("=", "+", "@")) for v in r.values()) for r in rows)
    assert any(r["title"].startswith("'=HYPERLINK") for r in rows)


def test_json_round_trips(synced):
    json.dumps(report.build_report(synced))


# ------------------------------------------------------------------ CLI

def test_cli_report_writes_files(synced, tmp_path, monkeypatch, capsys):
    from backend import library_cli
    monkeypatch.setattr(library_cli, "_db", lambda: synced)
    out = tmp_path / "r.html"
    library_cli.main(["report", "county", "--html", str(out), "--csv", str(tmp_path / "r.csv"), "--json", str(tmp_path / "r.json")])
    assert out.read_text().startswith("<!doctype html>") and (tmp_path / "r.csv").read_text().startswith("source,path")
    assert json.loads((tmp_path / "r.json").read_text())["overview"]["documents"] >= 4
    assert "Accessibility report" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        library_cli.main(["report", "no-such-source"])


def test_html_detail_sections_are_capped_but_the_table_and_csv_are_complete(synced, monkeypatch):
    monkeypatch.setattr(report, "MAX_DETAIL_DOCS", 1)
    r = report.build_report(synced)
    with_issues = [d for d in r["documents"] if d["id"] in r["attention"]]
    assert len(with_issues) >= 2
    h = report.render_html(r)
    assert h.count("<details") == 1 and "Details are shown for the 1 document(s)" in h
    assert h.count('href="#doc-') == 1                                       # only the documented one is a link
    for d in with_issues:
        assert d["path"].replace("&", "&amp;") in h                          # but every document is still in the table
    assert len(list(csv.DictReader(io.StringIO(report.render_csv(r))))) == sum(len(d["issues"]) for d in r["documents"])
