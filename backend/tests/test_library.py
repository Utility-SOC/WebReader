"""Library: connectors, allow rules, change detection, hold queue, metadata provenance, search, public API."""
import os
import shutil
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

docx = pytest.importorskip("docx")
pptx = pytest.importorskip("pptx")

from backend import ingest, search
from backend.connectors import AllowRules, FolderConnector
from backend.database import Base, get_db
from backend.library_models import Item, ItemDerivative, ItemMeta, Source
from backend.tests.pdfgen import Page, build_pdf


# ------------------------------------------------------------------ fixtures

@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    search.ensure_schema(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _docx(path, title="Water Rights Hearing Minutes", body="The board heard testimony about water rights on the river.", head="Water Rights", props=True):
    d = docx.Document()
    if props:
        d.core_properties.title = title
        d.core_properties.author = "Clerk Office"
    if head:
        d.add_heading(head, 1)
    d.add_paragraph(body)
    d.save(path)


def _pptx(path, title="County Budget"):
    prs = pptx.Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[0]); s.shapes.title.text = title; s.placeholders[1].text = "Fiscal year overview"
    prs.save(path)


def _pdf(path, text="Notice of public meeting about the new library budget and parking."):
    pg = Page(); pg.lines(72, 100, 11, [text, "Residents are invited to attend and comment."] * 3)
    with open(path, "wb") as f:
        f.write(build_pdf([pg], title="Public Meeting Notice", lang="en"))


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "public" / "planning").mkdir(parents=True)
    (r / "public" / "drafts").mkdir()
    (r / "private").mkdir()
    (r / ".hidden").mkdir()
    _docx(r / "public" / "planning" / "minutes.docx")
    _pptx(r / "public" / "budget.pptx")
    _pdf(r / "public" / "notice.pdf")
    (r / "public" / "notes.txt").write_text("Plain text notes about snow removal schedules on county roads.")
    _docx(r / "public" / "drafts" / "draft.docx", title="Draft", body="unreleased draft")
    _pdf(r / "private" / "secret.pdf", text="Confidential personnel matter.")
    _pdf(r / ".hidden" / "x.pdf")
    _docx(r / "public" / "~$minutes.docx")
    (r / "public" / "empty.pdf").write_bytes(b"")
    (r / "public" / "photo.png").write_bytes(b"\x89PNG")
    outside = tmp_path / "outside.pdf"; _pdf(outside, text="Outside the repository entirely.")
    os.symlink(outside, r / "public" / "escape.pdf")
    return r


def make_source(db, repo, **kw):
    s = Source(name="county", kind="folder", config={"root": str(repo)}, include=kw.pop("include", ["public/**"]),
               exclude=kw.pop("exclude", ["public/drafts/**"]), hold_new=kw.pop("hold_new", True),
               path_rules=kw.pop("path_rules", [{"prefix": "public/planning/", "agency": "Planning Commission", "tags": ["zoning", "minutes"]}]))
    db.add(s); db.commit()
    return s


# ------------------------------------------------------------------ allow rules + connector

def test_allow_rules_deny_by_default_and_exclude_wins():
    assert not AllowRules().allows("public/a.pdf")                      # nothing configured: nothing published
    r = AllowRules(["public/**"], ["public/drafts/**", "**/*.tmp.pdf"])
    assert r.allows("public/a.pdf") and r.allows("public/x/y/z.pdf") and r.allows("PUBLIC/A.PDF")
    assert not r.allows("private/a.pdf") and not r.allows("public/drafts/a.pdf") and not r.allows("public/x/b.tmp.pdf")
    assert AllowRules(["**"]).allows("anything/at/all.pdf")


def test_folder_connector_skips_junk_and_escapes(repo):
    paths = sorted(i.path for i in FolderConnector(str(repo)).list_items())
    assert "public/planning/minutes.docx" in paths and "private/secret.pdf" in paths   # listing is unfiltered; rules are applied by sync
    assert not any(p.startswith(".hidden") or "~$" in p or p.endswith("empty.pdf") or p.endswith(".png") or p.endswith("escape.pdf") for p in paths)


def test_folder_connector_refuses_path_traversal(repo, tmp_path):
    c = FolderConnector(str(repo))
    with pytest.raises(ValueError):
        with c.fetch("../outside.pdf"):
            pass
    with pytest.raises(ValueError):
        with c.fetch("public/escape.pdf"):   # symlink out of the root
            pass


# ------------------------------------------------------------------ sync

def test_dry_run_changes_nothing(db, repo):
    src = make_source(db, repo)
    rep = ingest.sync_source(db, src, dry_run=True)
    assert sorted(rep.new) == ["public/budget.pptx", "public/notes.txt", "public/notice.pdf", "public/planning/minutes.docx"]
    assert rep.not_allowed >= 2 and db.query(Item).count() == 0


def test_sync_processes_allowed_items_and_holds_them(db, repo):
    src = make_source(db, repo)
    rep = ingest.sync_source(db, src)
    assert len(rep.processed) == 4 and not rep.failed
    items = {i.path: i for i in db.query(Item).all()}
    assert set(items) == {"public/budget.pptx", "public/notes.txt", "public/notice.pdf", "public/planning/minutes.docx"}
    assert all(i.status == "ready" and not i.visible for i in items.values())          # held until released
    kinds = {d.kind for d in db.query(ItemDerivative).filter(ItemDerivative.item_id == items["public/planning/minutes.docx"].id)}
    assert {"text", "accessibility", "structure"} <= kinds
    assert search.search(db, "water")["total"] == 0                                    # hidden from readers
    assert search.search(db, "water", include_hidden=True)["total"] == 1


def test_metadata_has_provenance(db, repo):
    ingest.sync_source(db, make_source(db, repo))
    def meta(path):
        it = db.query(Item).filter(Item.path == path).one()
        return {(m.key, m.value): m for m in db.query(ItemMeta).filter(ItemMeta.item_id == it.id, ItemMeta.superseded.is_(False))}
    m = meta("public/planning/minutes.docx")
    assert m[("title", "Water Rights Hearing Minutes")].provenance == "original"
    assert m[("author", "Clerk Office")].provenance == "original"
    assert m[("agency", "Planning Commission")].provenance == "rule" and ("tag", "zoning") in m and ("folder", "public/planning") in m
    n = meta("public/notes.txt")                                   # no title anywhere: inferred from the file name, flagged as machine
    t = n[("title", "notes")]
    assert t.provenance == "machine" and t.confidence == 0.3


def test_second_sync_is_a_no_op_then_detects_a_change(db, repo):
    src = make_source(db, repo)
    ingest.sync_source(db, src)
    rep = ingest.sync_source(db, src)
    assert rep.unchanged == 4 and not rep.new and not rep.changed and not rep.processed
    time.sleep(0.01)
    _docx(repo / "public" / "planning" / "minutes.docx", title="Water Rights Hearing Minutes (Amended)")
    rep = ingest.sync_source(db, src)
    assert rep.changed == ["public/planning/minutes.docx"] and rep.processed == ["public/planning/minutes.docx"]
    it = db.query(Item).filter(Item.path == "public/planning/minutes.docx").one()
    assert it.title == "Water Rights Hearing Minutes (Amended)"
    history = db.query(ItemMeta).filter(ItemMeta.item_id == it.id, ItemMeta.key == "title").order_by(ItemMeta.id).all()
    assert [h.superseded for h in history] == [True, False]       # the old title is kept as history, not overwritten


def test_removed_files_leave_the_library(db, repo):
    src = make_source(db, repo, hold_new=False)
    ingest.sync_source(db, src)
    assert search.search(db, "snow")["total"] == 1
    (repo / "public" / "notes.txt").unlink()
    rep = ingest.sync_source(db, src)
    assert rep.removed == ["public/notes.txt"]
    assert search.search(db, "snow")["total"] == 0 and search.search(db, "snow", include_hidden=True)["total"] == 0


def test_one_bad_file_does_not_stop_the_rest(db, repo):
    (repo / "public" / "broken.docx").write_bytes(b"this is not a zip file at all")
    rep = ingest.sync_source(db, make_source(db, repo))
    assert len(rep.processed) == 4 and [p for p, _ in rep.failed] == ["public/broken.docx"]
    bad = db.query(Item).filter(Item.path == "public/broken.docx").one()
    assert bad.status == "failed" and bad.error and not bad.visible


def test_nothing_is_published_without_include_patterns(db, repo):
    src = make_source(db, repo, include=[])
    rep = ingest.sync_source(db, src)
    assert db.query(Item).count() == 0 and not rep.new


def test_release_and_withdraw(db, repo):
    src = make_source(db, repo)
    ingest.sync_source(db, src)
    assert ingest.release(db, src, ["public/notes.txt"]) == 1
    assert search.search(db, "snow")["total"] == 1 and search.search(db, "water")["total"] == 0
    assert ingest.release(db, src) == 3
    assert search.search(db, "water")["total"] == 1
    assert ingest.withdraw(db, src, ["public/planning/minutes.docx"]) == 1
    assert search.search(db, "water")["total"] == 0


def test_human_revision_supersedes_machine_value_and_keeps_history(db, repo):
    src = make_source(db, repo)
    ingest.sync_source(db, src)
    it = db.query(Item).filter(Item.path == "public/notes.txt").one()
    ingest.set_meta(db, it, "title", "Snow Removal Schedule", "human")
    db.commit()
    rows = db.query(ItemMeta).filter(ItemMeta.item_id == it.id, ItemMeta.key == "title").order_by(ItemMeta.id).all()
    assert [(r.provenance, r.superseded) for r in rows] == [("machine", True), ("human", False)]
    assert ingest.set_meta(db, it, "title", "Snow Removal Schedule", "human") is None    # no duplicate row for the same value


# ------------------------------------------------------------------ search

@pytest.fixture
def lib(db, repo):
    src = make_source(db, repo, hold_new=False)
    ingest.sync_source(db, src)
    return db


def test_search_ranks_filters_and_highlights(lib):
    r = search.search(lib, "water rights")
    assert r["total"] == 1 and r["results"][0]["title"] == "Water Rights Hearing Minutes"
    assert search.MARK_OPEN in r["results"][0]["snippet"]
    assert search.search(lib, "hear")["total"] == 1                       # prefix on the last word
    assert search.search(lib, "water snow")["total"] == 0                 # every word must match
    assert search.search(lib, "library parking")["total"] == 1             # found inside the PDF body
    assert search.search(lib, "budget")["total"] >= 1                      # pptx title


@pytest.mark.parametrize("nasty", ['"', 'water"', "water OR", "NEAR(", "*", "a AND", "'; DROP TABLE lib_items; --", "water*", "(((", "\\", "-"])
def test_search_survives_hostile_input(lib, nasty):
    search.search(lib, nasty)             # must not raise
    assert lib.query(Item).count() == 4   # and nothing was dropped


def test_search_filters_and_facets(lib):
    assert search.search(lib, agency="Planning Commission")["total"] == 1
    assert search.search(lib, tag="zoning")["total"] == 1 and search.search(lib, tag="nope")["total"] == 0
    assert search.search(lib, file_type="pdf")["total"] == 1 and search.search(lib, file_type="PDF")["total"] == 1
    assert search.search(lib, folder="public/planning")["total"] == 1
    assert search.search(lib)["total"] == 4                                  # browse with no query
    assert search.search(lib, date_from="2999-01-01")["total"] == 0
    f = search.facets(lib)
    assert f["agency"] == [{"value": "Planning Commission", "count": 1}]
    assert {x["value"] for x in f["type"]} == {"docx", "pptx", "pdf", "txt"}


def test_search_sorting_and_paging(lib):
    titles = [r["title"] for r in search.search(lib, sort="title")["results"]]
    assert titles == sorted(titles, key=str.lower)
    first = search.search(lib, sort="title", limit=2)["results"]
    second = search.search(lib, sort="title", limit=2, offset=2)["results"]
    assert len(first) == 2 and len(second) == 2 and {r["id"] for r in first}.isdisjoint({r["id"] for r in second})


# ------------------------------------------------------------------ public API

@pytest.fixture
def client(lib):
    from backend.main import app
    app.dependency_overrides[get_db] = lambda: lib
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_search_item_and_text(client, lib):
    r = client.get("/library/search", params={"q": "water"}).json()
    assert r["total"] == 1
    item_id = r["results"][0]["id"]
    detail = client.get(f"/library/items/{item_id}").json()
    assert detail["title"] == "Water Rights Hearing Minutes"
    prov = {(m["key"], m["provenance"]) for m in detail["metadata"]}
    assert ("title", "original") in prov and ("agency", "rule") in prov
    assert detail["accessibility"]["issue_summary"] == {"total": 0, "by_severity": {}, "by_fix": {}}   # this one is clean
    deck = client.get("/library/search", params={"q": "budget", "type": "pptx"}).json()["results"][0]["id"]
    assert client.get(f"/library/items/{deck}").json()["accessibility"]["issue_summary"]["total"] >= 1   # no title/language set
    text = client.get(f"/library/items/{item_id}/text").json()
    assert "testimony" in text["words"] and text["word_count"] > 5 and text["images"] == []
    assert client.get("/library/facets").json()["agency"][0]["value"] == "Planning Commission"


def test_api_never_leaks_paths_or_hidden_items(client, lib, repo):
    blob = client.get("/library/search").text + client.get("/library/items/1").text + client.get("/library/facets").text
    assert str(repo) not in blob and "secret.pdf" not in blob and "Confidential" not in blob
    ingest.withdraw(lib, lib.query(Source).one(), ["public/notes.txt"])
    hidden = lib.query(Item).filter(Item.path == "public/notes.txt").one().id
    assert client.get(f"/library/items/{hidden}").status_code == 404
    assert client.get(f"/library/items/{hidden}/text").status_code == 404
    assert client.get("/library/items/99999").status_code == 404


def test_api_validates_parameters(client):
    assert client.get("/library/search", params={"limit": 1000}).status_code == 422
    assert client.get("/library/search", params={"sort": "bogus"}).status_code == 422
    assert client.get("/library/search", params={"q": "x" * 500}).status_code == 422


def test_reading_room_exposes_the_library_but_not_uploads(client, monkeypatch):
    monkeypatch.setenv("WEBREADER_MODE", "reading_room")
    assert client.get("/library/search", params={"q": "water"}).status_code == 200
    assert client.post("/upload").status_code == 404 and client.post("/fetch_url", json={"url": "http://x"}).status_code == 404


# ------------------------------------------------------------------ CLI

def test_cli_refuses_a_source_with_no_include_pattern(capsys):
    from backend import library_cli
    with pytest.raises(SystemExit) as e:
        library_cli.main(["add-source", "x", "--root", "/tmp"])
    assert "no --include" in str(e.value)


def test_cli_rule_parsing():
    from backend.library_cli import _rule
    assert _rule("planning/=Planning Commission:zoning, land use") == {"prefix": "planning/", "agency": "Planning Commission", "tags": ["zoning", "land use"]}
    assert _rule("misc/=Clerk") == {"prefix": "misc/", "agency": "Clerk", "tags": []}
