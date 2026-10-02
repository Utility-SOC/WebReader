"""
Full-text search + browse over the library.

SQLite FTS5 today. The public surface (ensure_schema / index_item / remove /
search / facets) is deliberately small so a PostgreSQL implementation
(tsvector + GIN) can replace the SQL inside without touching callers.

Privacy: search terms are used to build one query and then dropped. Nothing
here logs or stores what a reader searched for.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .library_models import Item, ItemMeta

MARK_OPEN, MARK_CLOSE = "⟦", "⟧"   # ⟦ ⟧ : the UI highlights these itself; no HTML is returned
SINGLE_VALUED = {"title", "author", "created", "modified", "agency", "language", "doc_type", "folder", "summary"}


def ensure_schema(engine) -> None:
    if engine.dialect.name != "sqlite":
        raise NotImplementedError("Only the SQLite (FTS5) search backend exists so far; PostgreSQL is planned.")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS library_fts USING fts5(title, body, meta, tokenize='porter unicode61')"))


def fts_query(q: str) -> Optional[str]:
    """Turn what a person typed into a safe FTS5 expression: every word must appear; the last may be a prefix."""
    words = re.findall(r"[\w'-]+", q or "", flags=re.UNICODE)
    words = [w.strip("'-") for w in words if w.strip("'-")]
    if not words:
        return None
    parts = [f'"{w}"' for w in words[:-1]] + [f'"{words[-1]}"*']
    return " AND ".join(parts)


def active_meta(db: Session, item_id: int) -> Dict[str, List[str]]:
    rows = db.query(ItemMeta).filter(ItemMeta.item_id == item_id, ItemMeta.superseded.is_(False)).all()
    out: Dict[str, List[str]] = {}
    for r in rows:
        out.setdefault(r.key, []).append(r.value)
    return out


def index_item(db: Session, item: Item, body: str) -> None:
    meta = active_meta(db, item.id)
    meta_text = " ".join(f"{v}" for k in ("agency", "tag", "author", "folder", "doc_type") for v in meta.get(k, []))
    db.execute(text("DELETE FROM library_fts WHERE rowid = :id"), {"id": item.id})
    db.execute(text("INSERT INTO library_fts(rowid, title, body, meta) VALUES (:id, :t, :b, :m)"),
               {"id": item.id, "t": item.title or item.filename, "b": body or "", "m": meta_text})


def remove(db: Session, item_id: int) -> None:
    db.execute(text("DELETE FROM library_fts WHERE rowid = :id"), {"id": item_id})


def _meta_filter(key: str, param: str) -> str:
    return (f"EXISTS (SELECT 1 FROM lib_item_meta m WHERE m.item_id = i.id AND m.key = '{key}' "
            f"AND m.superseded = 0 AND lower(m.value) = lower(:{param}))")


def search(db: Session, q: Optional[str] = None, *, agency: Optional[str] = None, tag: Optional[str] = None,
           file_type: Optional[str] = None, folder: Optional[str] = None, date_from: Optional[str] = None,
           date_to: Optional[str] = None, sort: str = "relevance", limit: int = 20, offset: int = 0,
           include_hidden: bool = False) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 100)); offset = max(0, int(offset))
    where = ["i.status = 'ready'"]
    params: Dict[str, Any] = {}
    if not include_hidden:
        where.append("i.visible = 1")
    if agency:
        where.append(_meta_filter("agency", "agency")); params["agency"] = agency
    if tag:
        where.append(_meta_filter("tag", "tag")); params["tag"] = tag
    if folder:
        where.append(_meta_filter("folder", "folder")); params["folder"] = folder
    if file_type:
        where.append("i.file_type = :ft"); params["ft"] = file_type.lower()
    if date_from:
        where.append("i.doc_date >= :df"); params["df"] = date_from
    if date_to:
        where.append("i.doc_date <= :dt"); params["dt"] = date_to

    match = fts_query(q) if q else None
    if q and not match:
        return {"total": 0, "results": []}

    if match:
        cols = (f"i.id, snippet(library_fts, 1, '{MARK_OPEN}', '{MARK_CLOSE}', '\u2026', 24) AS snip, "
                "bm25(library_fts, 5.0, 1.0, 2.0) AS rank")
        source = "FROM library_fts JOIN lib_items i ON i.id = library_fts.rowid"
        where.insert(0, "library_fts MATCH :match"); params["match"] = match
        order = {"date": "i.doc_date DESC", "title": "lower(i.title) ASC"}.get(sort, "rank ASC")
    else:
        cols, source = "i.id, NULL AS snip, 0 AS rank", "FROM lib_items i"
        order = {"title": "lower(i.title) ASC"}.get(sort, "i.doc_date DESC")
    clause = " WHERE " + " AND ".join(where)

    total = db.execute(text(f"SELECT count(*) {source}{clause}"), params).scalar()
    rows = db.execute(text(f"SELECT {cols} {source}{clause} ORDER BY {order}, i.id LIMIT :lim OFFSET :off"),
                      {**params, "lim": limit, "off": offset}).all()
    return {"total": total, "results": describe(db, [(r[0], r[1]) for r in rows])}


def describe(db: Session, id_snips) -> List[Dict[str, Any]]:
    """Public summary of items (never includes filesystem paths)."""
    ids = [i for i, _ in id_snips]
    if not ids:
        return []
    items = {it.id: it for it in db.query(Item).filter(Item.id.in_(ids)).all()}
    meta: Dict[int, Dict[str, List[str]]] = {}
    title_source: Dict[int, str] = {}
    for r in db.query(ItemMeta).filter(ItemMeta.item_id.in_(ids), ItemMeta.superseded.is_(False)).all():
        meta.setdefault(r.item_id, {}).setdefault(r.key, []).append(r.value)
        if r.key == "title":
            title_source[r.item_id] = r.provenance
    out = []
    for i, snip in id_snips:
        it, m = items[i], meta.get(i, {})
        out.append({
            "id": i, "title": it.title or it.filename, "title_source": title_source.get(i), "file_type": it.file_type,
            "agency": (m.get("agency") or [None])[0], "tags": m.get("tag", []), "folder": (m.get("folder") or [None])[0],
            "date": it.doc_date.isoformat() if it.doc_date else None, "snippet": snip,
        })
    return out


def facets(db: Session, include_hidden: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    vis = "" if include_hidden else "AND i.visible = 1"
    out: Dict[str, List[Dict[str, Any]]] = {}
    for key in ("agency", "tag", "folder"):
        rows = db.execute(text(
            "SELECT m.value, count(DISTINCT i.id) c FROM lib_item_meta m JOIN lib_items i ON i.id = m.item_id "
            f"WHERE m.key = :k AND m.superseded = 0 AND i.status = 'ready' {vis} GROUP BY m.value ORDER BY c DESC, m.value LIMIT 200"),
            {"k": key}).all()
        out[key] = [{"value": v, "count": c} for v, c in rows]
    rows = db.execute(text(f"SELECT file_type, count(*) c FROM lib_items i WHERE status = 'ready' {vis} GROUP BY file_type ORDER BY c DESC")).all()
    out["type"] = [{"value": v, "count": c} for v, c in rows]
    return out
