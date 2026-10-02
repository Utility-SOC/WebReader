"""
Public, read-only library API (this is what a reading-room visitor can reach).

Only items an admin has released (visible) and that processed successfully are
ever returned. Nothing here exposes repository paths or credentials, and no
request parameters (search terms, item ids) are logged or stored. Admin
operations (adding sources, syncing, releasing) are not HTTP endpoints at all:
they live in the CLI, so there is nothing for an anonymous visitor to find.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import search
from .database import get_db
from .library_models import Item, ItemDerivative, ItemMeta, ItemStatus
from .utils import process_text

router = APIRouter(prefix="/library", tags=["library"])


def _visible_item(db: Session, item_id: int) -> Item:
    it = db.query(Item).filter(Item.id == item_id, Item.visible.is_(True), Item.status == ItemStatus.READY.value).first()
    if not it:
        raise HTTPException(404, "Not found")
    return it


@router.get("/search")
def library_search(q: Optional[str] = Query(None, max_length=200), agency: Optional[str] = None, tag: Optional[str] = None,
                   type: Optional[str] = None, folder: Optional[str] = None, date_from: Optional[str] = None,
                   date_to: Optional[str] = None, sort: str = Query("relevance", pattern="^(relevance|date|title)$"),
                   limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return search.search(db, q, agency=agency, tag=tag, file_type=type, folder=folder, date_from=date_from,
                         date_to=date_to, sort=sort, limit=limit, offset=offset)


@router.get("/facets")
def library_facets(db: Session = Depends(get_db)):
    return search.facets(db)


@router.get("/items/{item_id}")
def library_item(item_id: int, db: Session = Depends(get_db)):
    it = _visible_item(db, item_id)
    meta = (db.query(ItemMeta).filter(ItemMeta.item_id == it.id, ItemMeta.superseded.is_(False)).order_by(ItemMeta.id).all())
    acc = db.query(ItemDerivative).filter(ItemDerivative.item_id == it.id, ItemDerivative.kind == "accessibility").first()
    summary = (acc.data or {}).get("summary") if acc else None
    return {
        "id": it.id, "title": it.title or it.filename, "file_type": it.file_type,
        "date": it.doc_date.isoformat() if it.doc_date else None,
        # provenance is always shown: readers can see what is original and what a machine inferred
        "metadata": [{"key": m.key, "value": m.value, "provenance": m.provenance,
                      "confidence": m.confidence, "machine_generated": m.provenance == "machine"} for m in meta],
        "accessibility": {"issue_summary": summary},
    }


@router.get("/items/{item_id}/text")
def library_item_text(item_id: int, db: Session = Depends(get_db)):
    """The item's text in the same shape the reader loads (words / images / chapters)."""
    it = _visible_item(db, item_id)
    row = db.query(ItemDerivative).filter(ItemDerivative.item_id == it.id, ItemDerivative.kind == "text").first()
    words = process_text((row.data or {}).get("text", "")) if row else []
    return {"title": it.title or it.filename, "words": words, "word_count": len(words), "images": [], "chapters": []}
