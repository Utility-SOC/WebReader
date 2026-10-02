"""
Repository connectors: how WebReader sees a customer's document store.

A connector knows how to LIST what's there (with a cheap change fingerprint)
and how to FETCH one item to a local file. Everything else -- which items are
allowed, change detection, processing -- is the same for every kind of
repository, so SharePoint, S3, FTP and a plain folder differ only here.

Connectors are read-only by design: they never write to, move, or delete
anything in the customer's repository.

Safety default: the allow rules are DENY-BY-DEFAULT. A source with no include
patterns publishes nothing, so pointing WebReader at a repository can never
expose it wholesale by accident (the biggest exposure risk is non-public
documents sitting next to public ones).
"""

import contextlib
import fnmatch
import posixpath
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, List, Optional

# File types the processing pipeline can read (by extension, lower case, no dot).
SUPPORTED_EXTENSIONS = {"pdf", "docx", "pptx", "txt"}


@dataclass
class RemoteItem:
    path: str                     # repository-relative, forward slashes; the item's stable identity
    size: int
    modified: Optional[datetime]
    fingerprint: str              # changes whenever the content might have (etag, or size+mtime)
    extra: dict = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return posixpath.basename(self.path)

    @property
    def extension(self) -> str:
        return posixpath.splitext(self.path)[1].lstrip(".").lower()


class AllowRules:
    """Include/exclude glob patterns over repository-relative paths. Deny by default.

    A path is allowed when it matches at least one include pattern and no exclude
    pattern. '*' matches across folders too (so 'public/*' covers 'public/a/b.pdf').
    Matching is case-insensitive.
    """

    def __init__(self, include: Optional[List[str]] = None, exclude: Optional[List[str]] = None):
        self.include = [p.strip().lstrip("/") for p in (include or []) if p and p.strip()]
        self.exclude = [p.strip().lstrip("/") for p in (exclude or []) if p and p.strip()]

    @staticmethod
    def _match(path: str, pattern: str) -> bool:
        p, pat = path.lower(), pattern.lower()
        if pat in ("**", "**/*"):
            return True
        return fnmatch.fnmatchcase(p, pat) or fnmatch.fnmatchcase(p, pat.replace("**/", "*"))

    def allows(self, path: str) -> bool:
        if not self.include:
            return False
        if any(self._match(path, e) for e in self.exclude):
            return False
        return any(self._match(path, i) for i in self.include)


class Connector(ABC):
    kind = "abstract"

    @abstractmethod
    def list_items(self) -> Iterator[RemoteItem]:
        """Yield every item in the repository (allow rules are applied by the caller)."""

    @abstractmethod
    def fetch(self, path: str) -> "contextlib.AbstractContextManager[str]":
        """Context manager yielding a local filesystem path with the item's bytes."""
