"""Library tables: sources, items, metadata with provenance, and derived data.

Plain SQLAlchemy types only (JSON, DateTime, Text) so the same models run on
SQLite today and PostgreSQL later.

Provenance: every metadata value says where it came from -- "original" (in the
file / repository as authored), "rule" (an admin-configured rule, e.g. folder
-> agency), "machine" (a model inferred it; shown as such), or "human" (a
person wrote or approved it). Values are never overwritten: a revision adds a
row and marks the previous one superseded, so the history is the revision log.
"""

import enum

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint)
from sqlalchemy.sql import func

from .database import Base


class ItemStatus(str, enum.Enum):
    PENDING = "pending"          # new or changed; needs processing
    READY = "ready"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    REMOVED = "removed"          # no longer in the repository


class Provenance(str, enum.Enum):
    ORIGINAL = "original"
    RULE = "rule"
    MACHINE = "machine"
    HUMAN = "human"


class Source(Base):
    __tablename__ = "lib_sources"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    kind = Column(String, nullable=False)                  # folder | (s3, sftp, sharepoint ... later)
    config = Column(JSON, nullable=False, default=dict)    # connector settings; never secrets
    include = Column(JSON, nullable=False, default=list)   # allow patterns; EMPTY = publish nothing
    exclude = Column(JSON, nullable=False, default=list)
    hold_new = Column(Boolean, nullable=False, default=True)   # new items stay hidden until an admin releases them
    path_rules = Column(JSON, nullable=False, default=list)    # [{"prefix": "planning/", "agency": "...", "tags": [...]}]
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Item(Base):
    __tablename__ = "lib_items"
    __table_args__ = (UniqueConstraint("source_id", "path", name="uq_lib_item_path"),)

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("lib_sources.id"), nullable=False, index=True)
    path = Column(String, nullable=False)                  # repository-relative identity
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    size = Column(Integer, default=0)
    modified_at = Column(DateTime(timezone=True), nullable=True)   # when the repository says it last changed
    doc_date = Column(DateTime(timezone=True), nullable=True, index=True)  # the document's own date (for filtering/sorting)
    fingerprint = Column(String, nullable=False)
    status = Column(String, nullable=False, default=ItemStatus.PENDING.value, index=True)
    error = Column(Text, nullable=True)
    visible = Column(Boolean, nullable=False, default=False, index=True)   # shown to readers
    title = Column(String, nullable=True)                  # current best title (denormalised from metadata)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)


class ItemMeta(Base):
    __tablename__ = "lib_item_meta"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("lib_items.id"), nullable=False, index=True)
    key = Column(String, nullable=False, index=True)       # title author created agency tag language folder ...
    value = Column(Text, nullable=False)
    provenance = Column(String, nullable=False)
    confidence = Column(Float, nullable=True)
    model = Column(String, nullable=True)                  # model/version for machine values
    superseded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ItemDerivative(Base):
    """Things computed from an item's content: text, accessibility report, structure."""
    __tablename__ = "lib_item_derivatives"
    __table_args__ = (UniqueConstraint("item_id", "kind", name="uq_lib_derivative"),)

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("lib_items.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)                  # text | accessibility | structure
    fingerprint = Column(String, nullable=False)           # item fingerprint it was computed from
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
