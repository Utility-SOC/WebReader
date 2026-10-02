"""A plain folder (local disk, a mounted share, an NFS/SMB mount): the simplest connector."""

import contextlib
import os
from datetime import datetime, timezone
from typing import Iterator

from .base import Connector, RemoteItem, SUPPORTED_EXTENSIONS


class FolderConnector(Connector):
    kind = "folder"

    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        if not os.path.isdir(self.root):
            raise ValueError(f"Folder does not exist: {root}")

    def _safe(self, rel: str) -> str:
        """Absolute path for a repository-relative one, refusing anything that escapes the root."""
        full = os.path.realpath(os.path.join(self.root, rel))
        if full != self.root and not full.startswith(self.root + os.sep):
            raise ValueError("path escapes the repository root")
        return full

    def list_items(self) -> Iterator[RemoteItem]:
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                # hidden files and Office lock/temp files ("~$report.docx") are never documents
                if name.startswith((".", "~$")):
                    continue
                if os.path.splitext(name)[1].lstrip(".").lower() not in SUPPORTED_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, name)
                try:
                    real = os.path.realpath(full)
                    if not real.startswith(self.root + os.sep):   # a symlink pointing outside the root
                        continue
                    st = os.stat(real)
                except OSError:
                    continue
                if st.st_size == 0:
                    continue
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                yield RemoteItem(path=rel, size=st.st_size,
                                 modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                                 fingerprint=f"{st.st_size}-{st.st_mtime_ns}")

    @contextlib.contextmanager
    def fetch(self, path: str):
        yield self._safe(path)   # already local; nothing to download or clean up
