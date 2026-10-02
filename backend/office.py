"""Entry point the upload/worker paths use for Office files (and PDF accessibility facts)."""

import logging
from typing import Any, Dict, Tuple

from . import a11y_checks
from .extract_docx import extract_docx
from .extract_pdf import extract_pdf_structure
from .pdf_tags import inspect_tags
from .extract_pptx import extract_pptx

logger = logging.getLogger("SpeedReaderUtils")

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
    structure = None
    if not facts.get("tagged"):
        # Layout-based structure is a guess for PDFs that have none. Tagged PDFs are checked from their
        # real tag tree below, so this (slow, and bulky in the result) work is skipped for them.
        try:
            structure = extract_pdf_structure(path)
            issues = issues + a11y_checks.analyze(structure)
        except Exception as e:  # structure is an enhancement; the document-level facts still stand
            logger.warning(f"PDF structure extraction failed: {e}")
    if facts.get("tagged"):
        try:
            tag_facts, tag_issues = inspect_tags(path)
            facts.update(tag_facts)
            issues = issues + tag_issues
            if not tag_facts.get("display_doc_title") and facts.get("title"):
                issues.append(a11y_checks.Issue("PDF_DISPLAY_TITLE", a11y_checks.WARNING,
                                                "The window title will show the file name; set 'display document title' so it shows the document's title.",
                                                wcag="2.4.2", fix="auto"))
        except Exception as e:
            logger.warning(f"PDF tag inspection failed: {e}")
            issues.append(a11y_checks.Issue("PDF_TAG_TREE_NOT_INSPECTED", a11y_checks.INFO,
                                            "This PDF is tagged, but its tags could not be read, so its figures and tables were not checked.",
                                            fix="manual"))
    summary = a11y_checks.summarize(issues)
    truncated = facts.get("issues_truncated")
    if truncated:
        # The listing is capped per issue type; say so, and give the real totals.
        summary["truncated"] = truncated
        summary["total_found"] = summary["total"] - sum(min(n, 200) for n in truncated.values()) + sum(truncated.values())
    return {
        "format": "pdf",
        "title": facts.get("title", ""),
        "language": facts.get("language", ""),
        "facts": facts,
        "issues": [i.to_dict() for i in issues],
        "summary": summary,
        "structure": structure.to_dict() if structure else None,
    }
