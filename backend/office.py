"""Entry point the upload/worker paths use for Office files (and PDF accessibility facts)."""

from typing import Any, Dict, Tuple

from . import a11y_checks
from .extract_docx import extract_docx
from .extract_pptx import extract_pptx

OFFICE_TYPES = {"docx": extract_docx, "pptx": extract_pptx}


def process_office(path: str, file_type: str) -> Tuple[str, Dict[str, Any]]:
    """Return (reading_text, accessibility) for a .docx or .pptx file.

    `accessibility` is JSON-serialisable: the document's title/language, the
    list of open issues, a summary, and the structure the issues refer to.
    """
    structure = OFFICE_TYPES[file_type](path)
    issues = a11y_checks.analyze(structure)
    return structure.to_text(), {
        "format": structure.format,
        "title": structure.title,
        "language": structure.language,
        "issues": [i.to_dict() for i in issues],
        "summary": a11y_checks.summarize(issues),
        "structure": structure.to_dict(),
    }


def process_pdf_accessibility(path: str) -> Dict[str, Any]:
    facts, issues = a11y_checks.analyze_pdf(path)
    return {
        "format": "pdf",
        "title": facts.get("title", ""),
        "language": facts.get("language", ""),
        "facts": facts,
        "issues": [i.to_dict() for i in issues],
        "summary": a11y_checks.summarize(issues),
    }
