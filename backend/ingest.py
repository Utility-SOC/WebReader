"""
Library ingestion: list a repository, detect what's new/changed/gone, process what needs it.

  sync_source(db, source)     list -> allow rules -> upsert items -> process pending ones
  process_item(db, item, c)   fetch -> extract text -> accessibility analysis -> metadata -> search index

Nothing here writes to the repository. Items from a source with hold_new set
are processed but stay invisible to readers until an admin releases them.
"""

import logging
import os
import posixpath
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from . import search
from .connectors import AllowRules, Connector, SUPPORTED_EXTENSIONS, make_connector
from .library_models import Item, ItemDerivative, ItemMeta, ItemStatus, Provenance, Source

logger = logging.getLogger("SpeedReaderUtils")

MAX_STRUCTURE_BYTES = 5 * 1024 * 1024   # don't store a derivative bigger than this


@dataclass
class SyncReport:
    new: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    unchanged: int = 0
    removed: List[str] = field(default_factory=list)
    not_allowed: int = 0
    processed: List[str] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {"new": len(self.new), "changed": len(self.changed), "unchanged": self.unchanged,
                "removed": len(self.removed), "not_allowed": self.not_allowed,
                "processed": len(self.processed), "failed": len(self.failed)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- metadata

def set_meta(db: Session, item: Item, key: str, value: str, provenance: str, confidence: Optional[float] = None,
             model: Optional[str] = None) -> Optional[ItemMeta]:
    """Record a metadata value. Never overwrites: a changed value supersedes the old row (kept as history)."""
    value = (value or "").strip()
    if not value:
        return None
    current = db.query(ItemMeta).filter(ItemMeta.item_id == item.id, ItemMeta.key == key, ItemMeta.superseded.is_(False)).all()
    if any(c.value == value for c in current):
        return None
    if key in search.SINGLE_VALUED:
        for c in current:
            c.superseded = True
    row = ItemMeta(item_id=item.id, key=key, value=value, provenance=provenance, confidence=confidence, model=model)
    db.add(row)
    return row


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _pretty_stem(filename: str) -> str:
    stem = posixpath.splitext(filename)[0]
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", stem)).strip()


def apply_path_rules(source: Source, path: str) -> Tuple[Optional[str], List[str]]:
    """Admin-configured folder -> agency/tags rules. First matching prefix wins for agency; tags accumulate."""
    agency, tags = None, []
    low = path.lower()
    for rule in source.path_rules or []:
        if low.startswith(str(rule.get("prefix", "")).lower().lstrip("/")):
            agency = agency or rule.get("agency")
            tags.extend(rule.get("tags", []))
    return agency, tags


def derive_metadata(db: Session, item: Item, source: Source, acc: Optional[Dict[str, Any]]) -> None:
    structure = (acc or {}).get("structure") or {}
    meta = structure.get("metadata") or {}
    # title: the file's own title > first heading (inferred) > file name (inferred)
    title = (acc or {}).get("title") or ""
    if title.strip():
        set_meta(db, item, "title", title, Provenance.ORIGINAL.value)
    else:
        heads = [b for b in structure.get("blocks", []) if b.get("kind") in ("heading", "slide_title") and (b.get("text") or "").strip()]
        if heads:
            set_meta(db, item, "title", heads[0]["text"].strip()[:200], Provenance.MACHINE.value, 0.6, "layout-heuristic-v1")
        else:
            set_meta(db, item, "title", _pretty_stem(item.filename), Provenance.MACHINE.value, 0.3, "filename-v1")
    if meta.get("author"):
        set_meta(db, item, "author", meta["author"], Provenance.ORIGINAL.value)
    if (acc or {}).get("language"):
        set_meta(db, item, "language", acc["language"], Provenance.ORIGINAL.value)
    set_meta(db, item, "doc_type", item.file_type, Provenance.ORIGINAL.value)
    folder = posixpath.dirname(item.path)
    if folder:
        set_meta(db, item, "folder", folder, Provenance.ORIGINAL.value)
    agency, tags = apply_path_rules(source, item.path)
    if agency:
        set_meta(db, item, "agency", agency, Provenance.RULE.value)
    for t in tags:
        set_meta(db, item, "tag", t, Provenance.RULE.value)

    created = _parse_date(meta.get("created")) or _parse_date(meta.get("modified"))
    item.doc_date = created or item.modified_at
    db.flush()
    cur = [m.value for m in db.query(ItemMeta).filter(ItemMeta.item_id == item.id, ItemMeta.key == "title", ItemMeta.superseded.is_(False))]
    item.title = cur[0] if cur else _pretty_stem(item.filename)


# --------------------------------------------------------------------------- processing

def _extract(path: str, file_type: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """(reading text, accessibility report) for one local file."""
    from .office import OFFICE_TYPES, process_office, process_pdf_accessibility
    if file_type in OFFICE_TYPES:
        return process_office(path, file_type)
    if file_type == "pdf":
        from .utils import extract_text_from_pdf_range
        text, _images = extract_text_from_pdf_range(path, 1, ocr_verify_pages=3)   # ingestion is in the background: verify more
        return text, process_pdf_accessibility(path)
    if file_type == "txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(), None
    raise ValueError(f"unsupported type {file_type}")


def _store(db: Session, item: Item, kind: str, data: Any) -> None:
    row = db.query(ItemDerivative).filter(ItemDerivative.item_id == item.id, ItemDerivative.kind == kind).first()
    if row:
        row.data, row.fingerprint = data, item.fingerprint
    else:
        db.add(ItemDerivative(item_id=item.id, kind=kind, fingerprint=item.fingerprint, data=data))


def process_item(db: Session, item: Item, connector: Connector, source: Source) -> None:
    try:
        with connector.fetch(item.path) as local:
            text, acc = _extract(local, item.file_type)
        _store(db, item, "text", {"text": text})
        structure = None
        if acc is not None:
            acc = dict(acc)
            structure = acc.pop("structure", None)   # stored separately: it can be large
            _store(db, item, "accessibility", acc)
        if structure is not None:
            import json
            if len(json.dumps(structure)) <= MAX_STRUCTURE_BYTES:
                _store(db, item, "structure", structure)
        derive_metadata(db, item, source, {**acc, "structure": structure} if acc is not None else None)
        item.status, item.error, item.processed_at = ItemStatus.READY.value, None, _now()
        item.visible = not source.hold_new
        db.flush()
        search.index_item(db, item, text)
    except Exception as e:
        logger.error(f"Library: processing {item.path} failed: {e}")
        item.status, item.error = ItemStatus.FAILED.value, str(e)[:500]
        item.visible = False
        search.remove(db, item.id)
    db.commit()


def sync_source(db: Session, source: Source, connector: Optional[Connector] = None, *, dry_run: bool = False,
                process: bool = True) -> SyncReport:
    connector = connector or make_connector(source.kind, source.config)
    rules = AllowRules(source.include, source.exclude)
    report = SyncReport()
    seen = set()
    existing = {i.path: i for i in db.query(Item).filter(Item.source_id == source.id).all()}

    for ri in connector.list_items():
        if ri.extension not in SUPPORTED_EXTENSIONS or not rules.allows(ri.path):
            report.not_allowed += 1
            continue
        seen.add(ri.path)
        item = existing.get(ri.path)
        if item is None:
            report.new.append(ri.path)
            if not dry_run:
                item = Item(source_id=source.id, path=ri.path, filename=ri.filename, file_type=ri.extension, size=ri.size,
                            modified_at=ri.modified, fingerprint=ri.fingerprint, status=ItemStatus.PENDING.value, visible=False)
                db.add(item)
        elif item.fingerprint != ri.fingerprint or item.status in (ItemStatus.REMOVED.value,):
            report.changed.append(ri.path)
            if not dry_run:
                item.fingerprint, item.size, item.modified_at = ri.fingerprint, ri.size, ri.modified
                item.status, item.error = ItemStatus.PENDING.value, None
        else:
            report.unchanged += 1
        if item is not None and not dry_run:
            item.last_seen = _now()

    for path, item in existing.items():
        if path not in seen and item.status != ItemStatus.REMOVED.value:
            report.removed.append(path)
            if not dry_run:
                item.status, item.visible = ItemStatus.REMOVED.value, False
                search.remove(db, item.id)
    if dry_run:
        return report
    db.commit()

    if process:
        pending = db.query(Item).filter(Item.source_id == source.id, Item.status == ItemStatus.PENDING.value).all()
        for item in pending:
            process_item(db, item, connector, source)
            (report.processed if item.status == ItemStatus.READY.value else report.failed).append(
                item.path if item.status == ItemStatus.READY.value else (item.path, item.error or ""))
    return report


def release(db: Session, source: Source, paths: Optional[List[str]] = None) -> int:
    """Make held items visible to readers (all ready items of the source, or just the given paths)."""
    q = db.query(Item).filter(Item.source_id == source.id, Item.status == ItemStatus.READY.value, Item.visible.is_(False))
    if paths:
        q = q.filter(Item.path.in_(paths))
    items = q.all()
    for it in items:
        it.visible = True
    db.commit()
    return len(items)


def withdraw(db: Session, source: Source, paths: List[str]) -> int:
    """Hide items again (e.g. one turned out not to be public)."""
    items = db.query(Item).filter(Item.source_id == source.id, Item.path.in_(paths)).all()
    for it in items:
        it.visible = False
    db.commit()
    return len(items)
