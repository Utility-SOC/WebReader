"""
Admin accessibility report for the library.

build_report() turns what ingestion recorded (each item's accessibility issues, its processing status, which
metadata a machine inferred) into one structure; three renderers present it:

  render_text   a short terminal summary
  render_csv    one row per issue, for spreadsheets
  render_html   a single self-contained, accessible page: no scripts, no external requests, strict CSP

The report is for ADMINS and deliberately not an HTTP endpoint: it contains repository paths and document titles
that must never be public. It lists what the automatic checks found; it is not a compliance claim, and the report
says so.
"""

import csv
import html
import io
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .library_models import Item, ItemDerivative, ItemMeta, ItemStatus, Source
from .report_guidance import WCAG_NAMES, describe

MAX_ISSUES_PER_DOC = 50
MAX_DETAIL_DOCS = 1000       # documents given an expanded details section in the HTML (the table lists all; the CSV has everything)
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
SEVERITY_LABEL = {"error": "Error", "warning": "Warning", "info": "Notice"}
FIX_LABEL = {
    "auto": "Can be fixed automatically",
    "suggest": "Software can suggest a fix; a person confirms",
    "manual": "A person must fix it",
}


def _n(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- aggregation

def build_report(db: Session, source_name: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    q = db.query(Source)
    if source_name:
        q = q.filter(Source.name == source_name)
    sources = q.all()
    if source_name and not sources:
        raise ValueError(f"No source named '{source_name}'")
    src_by_id = {s.id: s for s in sources}
    items = db.query(Item).filter(Item.source_id.in_(list(src_by_id) or [-1])).order_by(Item.path).all()
    ids = [i.id for i in items] or [-1]

    acc_by_item = {d.item_id: d.data for d in db.query(ItemDerivative).filter(ItemDerivative.item_id.in_(ids), ItemDerivative.kind == "accessibility")}
    machine_meta: Dict[int, List[str]] = defaultdict(list)
    for m in db.query(ItemMeta).filter(ItemMeta.item_id.in_(ids), ItemMeta.superseded.is_(False), ItemMeta.provenance == "machine"):
        machine_meta[m.item_id].append(m.key)

    docs: List[Dict[str, Any]] = []
    code_docs: Dict[str, set] = defaultdict(set)
    code_count: Counter = Counter()
    code_info: Dict[str, Dict[str, Any]] = {}
    for it in items:
        acc = acc_by_item.get(it.id) or {}
        issues = acc.get("issues") or []
        summary = acc.get("summary") or {}
        truncated = (summary.get("truncated") or {})
        per_code = Counter(i["code"] for i in issues)
        for code, total in truncated.items():          # the stored listing is capped; the true total is kept alongside
            per_code[code] = total
        sev = Counter()
        for i in issues:
            sev[i["severity"]] += 1
        for code, n in per_code.items():
            code_docs[code].add(it.id)
            code_count[code] += n
        for i in issues:
            code_info.setdefault(i["code"], {"severity": i["severity"], "wcag": i.get("wcag", ""), "fix": i.get("fix", "manual")})
        shown = sorted(issues, key=lambda i: (SEVERITY_ORDER.get(i["severity"], 9), i["code"], i.get("location", "")))
        docs.append({
            "id": it.id, "source": src_by_id[it.source_id].name, "title": it.title or it.filename, "path": it.path,
            "type": it.file_type, "status": it.status, "visible": bool(it.visible), "error_message": it.error,
            "analysed": bool(acc),
            "errors": sev["error"], "warnings": sev["warning"], "notices": sev["info"],
            "issue_total": sum(per_code.values()), "codes": dict(per_code),
            "issues": shown[:MAX_ISSUES_PER_DOC], "issues_not_shown": max(0, len(shown) - MAX_ISSUES_PER_DOC),
            "machine_fields": sorted(set(machine_meta.get(it.id, []))),
        })

    ready = [d for d in docs if d["status"] == ItemStatus.READY.value]
    analysed = [d for d in ready if d["analysed"]]
    clean = [d for d in analysed if d["issue_total"] == 0]
    by_code = []
    for code, n in code_count.items():
        g = describe(code); inf = code_info.get(code, {})
        by_code.append({"code": code, "title": g["title"], "why": g["why"], "how": g["how"],
                        "severity": inf.get("severity", "warning"), "wcag": inf.get("wcag", ""),
                        "wcag_name": WCAG_NAMES.get(inf.get("wcag", ""), ""), "fix": inf.get("fix", "manual"),
                        "documents": len(code_docs[code]), "occurrences": n})
    by_code.sort(key=lambda c: (SEVERITY_ORDER.get(c["severity"], 9), -c["documents"], -c["occurrences"], c["code"]))

    by_fix = Counter()
    by_wcag: Counter = Counter()
    for c in by_code:
        by_fix[c["fix"]] += c["occurrences"]
        if c["wcag"]:
            by_wcag[c["wcag"]] += c["occurrences"]

    attention = sorted((d for d in analysed if d["errors"] or d["issue_total"]), key=lambda d: (-d["errors"], -d["issue_total"], d["path"]))
    return {
        "generated_at": (now or _now()).isoformat(timespec="seconds"),
        "sources": [s.name for s in sources],
        "overview": {
            "documents": len(docs), "ready": len(ready), "released": sum(1 for d in docs if d["visible"]),
            "held": sum(1 for d in ready if not d["visible"]),
            "failed": sum(1 for d in docs if d["status"] == ItemStatus.FAILED.value),
            "unsupported": sum(1 for d in docs if d["status"] == ItemStatus.UNSUPPORTED.value),
            "removed": sum(1 for d in docs if d["status"] == ItemStatus.REMOVED.value),
            "analysed": len(analysed), "not_checked": len(ready) - len(analysed), "clean": len(clean),
            "with_errors": sum(1 for d in analysed if d["errors"]),
            "issues": sum(code_count.values()),
            "errors": sum(c["occurrences"] for c in by_code if c["severity"] == "error"),
            "warnings": sum(c["occurrences"] for c in by_code if c["severity"] == "warning"),
            "notices": sum(c["occurrences"] for c in by_code if c["severity"] == "info"),
        },
        "by_code": by_code,
        "by_fix": {k: by_fix.get(k, 0) for k in ("auto", "suggest", "manual")},
        "by_wcag": [{"criterion": k, "name": WCAG_NAMES.get(k, ""), "occurrences": v} for k, v in sorted(by_wcag.items())],
        "documents": docs,
        "attention": [d["id"] for d in attention],
        "problems": [{"path": d["path"], "status": d["status"], "error": d["error_message"]} for d in docs
                     if d["status"] in (ItemStatus.FAILED.value, ItemStatus.UNSUPPORTED.value)],
        "machine_titles": [{"id": d["id"], "title": d["title"], "path": d["path"]} for d in ready if "title" in d["machine_fields"]],
    }


# --------------------------------------------------------------------------- text

def render_text(r: Dict[str, Any]) -> str:
    o = r["overview"]
    out = [f"Accessibility report ({', '.join(r['sources']) or 'no sources'}), {r['generated_at']}", ""]
    out.append(f"Documents: {o['documents']} ({o['ready']} processed, {o['released']} released, {o['held']} held, {o['failed']} failed, {o['unsupported']} unsupported, {o['removed']} removed)")
    out.append(f"Checked: {o['analysed']}" + (f" (+{o['not_checked']} of a type with no accessibility checks, e.g. plain text)" if o["not_checked"] else "")
               + f"; with no issues found: {o['clean']}; with at least one error: {o['with_errors']}")
    out.append(f"Issues: {o['issues']} ({_n(o['errors'], 'error')}, {_n(o['warnings'], 'warning')}, {_n(o['notices'], 'notice')})")
    f = r["by_fix"]
    out.append(f"How they can be fixed: {f['auto']} automatically, {f['suggest']} with a software suggestion a person confirms, {f['manual']} by a person")
    out += ["", "Most common problems:"]
    for c in r["by_code"][:10]:
        out.append(f"  [{SEVERITY_LABEL[c['severity']]:7}] {c['title']}: {c['occurrences']} in {c['documents']} document(s)")
    out += ["", "Documents needing the most attention:"]
    by_id = {d["id"]: d for d in r["documents"]}
    for did in r["attention"][:10]:
        d = by_id[did]
        out.append(f"  {d['errors']:3} error(s), {d['issue_total']:3} issue(s)  {d['title']}  ({d['path']})")
    if r["problems"]:
        out += ["", "Could not be processed:"] + [f"  {p['path']}: {p['error'] or p['status']}" for p in r["problems"]]
    out += ["", "These are the results of automatic checks. They are not a compliance claim: a document with no issues found can still be inaccessible."]
    return "\n".join(out)


# --------------------------------------------------------------------------- csv

def _csv_safe(v: Any) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s     # spreadsheets run cells that start like a formula


def render_csv(r: Dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["source", "path", "title", "type", "status", "released", "severity", "problem", "code", "location", "wcag", "fix", "detail"])
    for d in r["documents"]:
        for i in d["issues"]:
            g = describe(i["code"])
            w.writerow([_csv_safe(x) for x in (d["source"], d["path"], d["title"], d["type"], d["status"], "yes" if d["visible"] else "no",
                                               SEVERITY_LABEL.get(i["severity"], i["severity"]), g["title"], i["code"], i.get("location", ""),
                                               i.get("wcag", ""), i.get("fix", ""), i.get("message", ""))])
    return buf.getvalue()


# --------------------------------------------------------------------------- html

_e = html.escape

CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1a1d24;--muted:#4b5563;--line:#cbd2dc;--card:#f5f7fa;--link:#1d4ed8;
--err-bg:#fde8e8;--err-fg:#8a1111;--warn-bg:#fff3d6;--warn-fg:#6b4500;--info-bg:#e6eefb;--info-fg:#1e3a6e;--ok-bg:#e1f4e6;--ok-fg:#0f5a26}
@media (prefers-color-scheme:dark){:root{--bg:#10131a;--fg:#e8ebf2;--muted:#b4bccb;--line:#38404f;--card:#181c26;--link:#8ab4ff;
--err-bg:#4a1a1a;--err-fg:#ffd3d3;--warn-bg:#4a3a10;--warn-fg:#ffe2a3;--info-bg:#1b2c4d;--info-fg:#cfe0ff;--ok-bg:#163a22;--ok-fg:#c7f0d2}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--link)}a:focus-visible,summary:focus-visible{outline:3px solid var(--link);outline-offset:2px}
.skip{position:absolute;left:-999px;top:0;background:var(--link);color:var(--bg);padding:.6rem 1rem;z-index:10}.skip:focus{left:0}
header,main,footer{max-width:72rem;margin:0 auto;padding:0 1rem}header{padding-top:1.5rem}
h1{font-size:1.9rem;margin:.2rem 0}h2{font-size:1.4rem;margin:2.2rem 0 .6rem;border-bottom:2px solid var(--line);padding-bottom:.3rem}h3{font-size:1.1rem;margin:1.2rem 0 .4rem}
.notice{background:var(--warn-bg);color:var(--warn-fg);border:1px solid var(--line);border-radius:.5rem;padding:.7rem 1rem}
nav ul{display:flex;flex-wrap:wrap;gap:.5rem 1.2rem;list-style:none;padding:0;margin:1rem 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:.8rem;margin:0;padding:0;list-style:none}
.cards li{background:var(--card);border:1px solid var(--line);border-radius:.6rem;padding:.7rem .9rem}.cards .n{display:block;font-size:1.8rem;font-weight:700}
.cards .l{color:var(--muted);font-size:.9rem}
table{border-collapse:collapse;width:100%;margin:.6rem 0 1rem;font-size:.95rem}caption{text-align:left;font-weight:600;padding:.3rem 0;color:var(--muted)}
th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:.45rem .6rem}th{background:var(--card)}
.wrap{overflow-x:auto}
.sev{display:inline-block;border-radius:.3rem;padding:.05rem .45rem;font-weight:700;font-size:.85rem;white-space:nowrap}
.sev.error{background:var(--err-bg);color:var(--err-fg)}.sev.warning{background:var(--warn-bg);color:var(--warn-fg)}.sev.info{background:var(--info-bg);color:var(--info-fg)}.sev.ok{background:var(--ok-bg);color:var(--ok-fg)}
details{border:1px solid var(--line);border-radius:.5rem;margin:.5rem 0;background:var(--card)}summary{cursor:pointer;padding:.6rem .9rem;font-weight:600}
details>.body{padding:0 .9rem .6rem}.muted{color:var(--muted)}.path{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85rem;overflow-wrap:anywhere}
@media print{details{border:none}.skip,nav{display:none}}
"""


def _sev(s: str) -> str:
    sym = {"error": "✖", "warning": "▲", "info": "ℹ"}.get(s, "")
    return f'<span class="sev {_e(s)}"><span aria-hidden="true">{sym}</span> {_e(SEVERITY_LABEL.get(s, s))}</span>'


def render_html(r: Dict[str, Any]) -> str:
    o = r["overview"]
    names = ", ".join(r["sources"]) or "no sources"
    when = r["generated_at"]
    docs = r["documents"]
    p: List[str] = []
    add = p.append
    add('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">')
    add("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">")
    add(f"<title>Accessibility report: {_e(names)}, {_e(when[:10])}</title><style>{CSS}</style></head><body>")
    add('<a class="skip" href="#main">Skip to the report</a>')
    add(f'<header><h1>Accessibility report</h1><p class="muted">Library sources: {_e(names)}. Generated {_e(when)}.</p>')
    add('<p class="notice"><strong>Internal document.</strong> It lists repository file paths and document titles. Do not publish it.</p>')
    add('<nav aria-label="Report sections"><ul><li><a href="#overview">Overview</a></li><li><a href="#priorities">What to fix first</a></li>'
        '<li><a href="#documents">Documents</a></li><li><a href="#details">Document details</a></li><li><a href="#problems">Processing problems</a></li>'
        '<li><a href="#machine">Machine-generated titles</a></li><li><a href="#about">About this report</a></li></ul></nav></header><main id="main">')

    # overview
    add('<section aria-labelledby="overview"><h2 id="overview">Overview</h2><ul class="cards">')
    for n, label in ((o["documents"], "documents in the library"), (o["analysed"], "documents checked"), (o["clean"], "with no issues found"),
                     (o["with_errors"], "with at least one error"), (o["issues"], "issues in total"), (o["held"], "processed but not yet released")):
        add(f'<li><span class="n">{n}</span><span class="l">{_e(label)}</span></li>')
    add("</ul>")
    if o["not_checked"]:
        add(f'<p class="muted">{o["not_checked"]} document(s) are of a type that has no accessibility checks (for example plain text) and are not counted as checked.</p>')
    add(f'<p>The {o["issues"]} issues are <strong>{_n(o["errors"], "error")}</strong>, <strong>{_n(o["warnings"], "warning")}</strong> and '
        f'<strong>{_n(o["notices"], "notice")}</strong>.</p>')
    f = r["by_fix"]
    add('<table><caption>How the issues can be fixed</caption><thead><tr><th scope="col">Kind of fix</th><th scope="col">Issues</th></tr></thead><tbody>')
    for k in ("auto", "suggest", "manual"):
        add(f"<tr><th scope=\"row\">{_e(FIX_LABEL[k])}</th><td>{f[k]}</td></tr>")
    add("</tbody></table>")
    if r["by_wcag"]:
        add('<div class="wrap"><table><caption>Issues by WCAG success criterion</caption><thead><tr><th scope="col">Criterion</th><th scope="col">Name</th><th scope="col">Issues</th></tr></thead><tbody>')
        for w in r["by_wcag"]:
            add(f'<tr><th scope="row">{_e(w["criterion"])}</th><td>{_e(w["name"])}</td><td>{w["occurrences"]}</td></tr>')
        add("</tbody></table></div>")
    add("</section>")

    # priorities
    add('<section aria-labelledby="priorities"><h2 id="priorities">What to fix first</h2>')
    if r["by_code"]:
        add('<p>Problems that affect the most documents, errors first. Each row says why it matters to a reader and how to fix it.</p>')
        add('<div class="wrap"><table><caption>Problems found, most serious and widespread first</caption><thead><tr>'
            '<th scope="col">Severity</th><th scope="col">Problem</th><th scope="col">Documents</th><th scope="col">Times</th><th scope="col">Why it matters</th><th scope="col">How to fix it</th></tr></thead><tbody>')
        for c in r["by_code"]:
            wc = f' <span class="muted">(WCAG {_e(c["wcag"])})</span>' if c["wcag"] else ""
            add(f'<tr><td>{_sev(c["severity"])}</td><th scope="row">{_e(c["title"])}{wc}<br><span class="muted">{_e(FIX_LABEL.get(c["fix"], c["fix"]))}</span></th>'
                f'<td>{c["documents"]}</td><td>{c["occurrences"]}</td><td>{_e(c["why"])}</td><td>{_e(c["how"])}</td></tr>')
        add("</tbody></table></div>")
    else:
        add("<p>No issues were found by the automatic checks.</p>")
    add("</section>")

    # documents
    add('<section aria-labelledby="documents"><h2 id="documents">Documents</h2><p>Documents with the most errors first. Select a title to jump to its details.</p>')
    order = {did: n for n, did in enumerate(r["attention"])}
    rest = [d for d in docs if d["id"] not in order]
    listed = [d for d in docs if d["id"] in order]
    listed.sort(key=lambda d: order[d["id"]])
    detailed = {d["id"] for d in listed[:MAX_DETAIL_DOCS]}
    add('<div class="wrap"><table><caption>All documents in this report</caption><thead><tr><th scope="col">Document</th><th scope="col">Kind</th>'
        '<th scope="col">State</th><th scope="col">Errors</th><th scope="col">Warnings</th><th scope="col">Notices</th></tr></thead><tbody>')
    for d in listed + rest:
        state = ("Released" if d["visible"] else "Held (not public)") if d["status"] == "ready" else d["status"].capitalize()
        if d["status"] == "ready" and d["analysed"] and d["issue_total"] == 0:
            state += " · no issues found"
        name = f'<a href="#doc-{d["id"]}">{_e(d["title"])}</a>' if d["id"] in detailed else _e(d["title"])
        add(f'<tr><th scope="row">{name}<br><span class="path">{_e(d["path"])}</span></th><td>{_e(d["type"].upper())}</td>'
            f'<td>{_e(state)}</td><td>{d["errors"]}</td><td>{d["warnings"]}</td><td>{d["notices"]}</td></tr>')
    add("</tbody></table></div></section>")

    # details
    add('<section aria-labelledby="details"><h2 id="details">Document details</h2>')
    shown = listed[:MAX_DETAIL_DOCS]
    if not shown:
        add("<p>No document has issues to show.</p>")
    if len(listed) > len(shown):
        add(f'<p class="muted">Details are shown for the {len(shown)} document(s) with the most errors. The other {len(listed) - len(shown)} documents with issues are in the table above, and the CSV export lists every issue.</p>')
    for d in shown:
        add(f'<details id="doc-{d["id"]}"><summary>{_e(d["title"])} <span class="muted">– {_n(d["errors"], "error")}, {_n(d["warnings"], "warning")}, {_n(d["notices"], "notice")}</span></summary><div class="body">')
        add(f'<p class="path">{_e(d["source"])}: {_e(d["path"])}</p>')
        if d["machine_fields"]:
            add(f'<p><span class="sev info">Machine-generated</span> These details were inferred by software and have not been reviewed: {_e(", ".join(d["machine_fields"]))}.</p>')
        add('<div class="wrap"><table><caption>Issues in this document</caption><thead><tr><th scope="col">Severity</th><th scope="col">Where</th><th scope="col">Problem</th><th scope="col">Fix</th></tr></thead><tbody>')
        for i in d["issues"]:
            g = describe(i["code"])
            add(f'<tr><td>{_sev(i["severity"])}</td><td>{_e(i.get("location") or "Whole document")}</td><td><strong>{_e(g["title"])}</strong><br>{_e(i.get("message", ""))}</td>'
                f'<td>{_e(FIX_LABEL.get(i.get("fix", ""), i.get("fix", "")))}</td></tr>')
        add("</tbody></table></div>")
        if d["issues_not_shown"]:
            add(f'<p class="muted">{d["issues_not_shown"]} more issue(s) in this document are not listed here; the CSV export has the stored list.</p>')
        add("</div></details>")
    add("</section>")

    # processing problems
    add('<section aria-labelledby="problems"><h2 id="problems">Processing problems</h2>')
    if r["problems"]:
        add('<p>These files could not be read, so they have not been checked and are not in the library.</p><div class="wrap"><table><caption>Files that could not be processed</caption><thead><tr><th scope="col">File</th><th scope="col">State</th><th scope="col">Reason</th></tr></thead><tbody>')
        for x in r["problems"]:
            add(f'<tr><th scope="row" class="path">{_e(x["path"])}</th><td>{_e(x["status"].capitalize())}</td><td>{_e(x["error"] or "")}</td></tr>')
        add("</tbody></table></div>")
    else:
        add("<p>Every file was processed.</p>")
    add("</section>")

    # machine-generated titles
    add('<section aria-labelledby="machine"><h2 id="machine">Machine-generated titles awaiting review</h2>')
    if r["machine_titles"]:
        add(f'<p>{len(r["machine_titles"])} document(s) have no title of their own, so software worked one out (from the first heading or the file name). '
            'Readers see these labelled as software-generated until a person reviews them.</p><ul>')
        for m in r["machine_titles"]:
            add(f'<li>{_e(m["title"])} <span class="path">({_e(m["path"])})</span></li>')
        add("</ul>")
    else:
        add("<p>None: every title came from the document itself or was set by a person.</p>")
    add("</section>")

    # about
    add('<section aria-labelledby="about"><h2 id="about">About this report</h2>'
        '<p>These are the results of <strong>automatic checks</strong>. They find problems a program can detect (missing alternative text, '
        'missing titles and language, skipped heading levels, untagged or unreadable PDFs, and similar). They cannot judge whether alternative '
        'text is accurate or whether a document is easy to follow, so <strong>a document with no issues found can still be inaccessible</strong>, '
        'and this report is not a statement of compliance with any standard.</p>'
        '<p>Tables are checked as pictures: they need a description rather than a rebuilt header structure. '
        'Severity is always written out (Error, Warning, Notice) as well as shown by colour.</p></section>')
    add(f'</main><footer><p class="muted">Generated by WebReader on {_e(when)}.</p></footer></body></html>')
    return "".join(p)
