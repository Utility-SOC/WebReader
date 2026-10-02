from typing import Any, Dict

from .base import AllowRules, Connector, RemoteItem, SUPPORTED_EXTENSIONS  # noqa: F401
from .folder import FolderConnector


def make_connector(kind: str, config: Dict[str, Any]) -> Connector:
    """Build a connector from a source's stored kind + config (config never holds secrets)."""
    if kind == "folder":
        return FolderConnector(config["root"])
    raise ValueError(f"Unknown connector kind '{kind}' (available: folder)")
