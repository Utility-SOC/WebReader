"""DOCX -> DocumentStructure (reading order, headings, lists, tables, figures + their alt text)."""

import re
from typing import List

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .structure import (Block, DocumentStructure, HEADING, PARAGRAPH, LIST_ITEM, TABLE, FIGURE)

_HEADING_RE = re.compile(r"^heading\s*(\d)$", re.I)


def _local(el, name):
    """First descendant whose local tag name is `name` (namespace-agnostic)."""
    found = el.xpath(f".//*[local-name()='{name}']")
    return found[0] if found else None


def _figure_type(drawing) -> str:
    uri = ""
    gd = _local(drawing, "graphicData")
    if gd is not None:
        uri = gd.get("uri", "")
    if uri.endswith("/chart"):
        return "chart"
    if uri.endswith("/diagram"):
        return "diagram"
    if uri.endswith("/picture"):
        return "picture"
    if "wordprocessingShape" in uri or "wordprocessingGroup" in uri:
        return "shape"
    return "picture"


def _iter_body(document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _heading_level(par: Paragraph) -> int:
    name = (par.style.name if par.style is not None else "") or ""
    if name.lower() == "title":
        return 1
    m = _HEADING_RE.match(name)
    if m:
        return int(m.group(1))
    # custom styles can still carry an outline level
    lvl = par._p.xpath("./w:pPr/w:outlineLvl/@w:val")
    if lvl and lvl[0].isdigit() and int(lvl[0]) < 9:
        return int(lvl[0]) + 1
    return 0


def _is_list(par: Paragraph) -> bool:
    name = (par.style.name if par.style is not None else "") or ""
    return name.lower().startswith("list") or bool(par._p.xpath("./w:pPr/w:numPr"))


def _table_block(tbl: Table, location: str) -> Block:
    rows: List[List[str]] = []
    for r in tbl.rows:
        seen, cells = set(), []
        for c in r.cells:  # merged cells repeat the same object; keep each once
            if id(c._tc) in seen:
                continue
            seen.add(id(c._tc))
            cells.append(c.text.strip())
        rows.append(cells)
    first_tr = tbl._tbl.xpath("./w:tr")[0] if tbl._tbl.xpath("./w:tr") else None
    repeat_header = bool(first_tr is not None and first_tr.xpath("./w:trPr/w:tblHeader"))
    look = tbl._tbl.xpath("./w:tblPr/w:tblLook/@w:firstRow")
    style_header = bool(look and look[0] in ("1", "true"))
    return Block(kind=TABLE, rows=rows, header_row=repeat_header, location=location,
                 extra={"header_row_style": style_header, "merged": bool(tbl._tbl.xpath(".//w:gridSpan|.//w:vMerge"))})


def extract_docx(path: str) -> DocumentStructure:
    document = docx.Document(path)
    cp = document.core_properties
    lang = ""
    langs = document.styles.element.xpath(".//w:docDefaults//w:lang/@w:val")
    if langs:
        lang = langs[0]
    lang = lang or (cp.language or "")

    s = DocumentStructure(
        format="docx", title=(cp.title or "").strip(), language=lang,
        metadata={"author": cp.author or "", "created": str(cp.created or ""), "modified": str(cp.modified or ""),
                  "subject": cp.subject or "", "keywords": cp.keywords or ""})

    n_par = n_tbl = 0
    for item in _iter_body(document):
        if isinstance(item, Table):
            n_tbl += 1
            s.blocks.append(_table_block(item, f"Table {n_tbl}"))
            continue

        n_par += 1
        loc = f"Paragraph {n_par}"
        text = item.text.strip()
        level = _heading_level(item)
        if text:
            if level:
                s.blocks.append(Block(kind=HEADING, text=text, level=level, location=loc))
            elif _is_list(item):
                ilvl = item._p.xpath("./w:pPr/w:numPr/w:ilvl/@w:val")
                s.blocks.append(Block(kind=LIST_ITEM, text=text, level=int(ilvl[0]) if ilvl else 0, location=loc))
            else:
                s.blocks.append(Block(kind=PARAGRAPH, text=text, location=loc))

        for drawing in item._p.xpath(".//w:drawing"):
            docpr = _local(drawing, "docPr")
            descr = (docpr.get("descr") or "").strip() if docpr is not None else ""
            name = (docpr.get("name") or "") if docpr is not None else ""
            decorative = _local(drawing, "decorative") is not None
            ftype = _figure_type(drawing)
            # text inside text boxes / shapes is real content that p.text doesn't include
            for tx in drawing.xpath(".//*[local-name()='txbxContent']"):
                box = " ".join(t.text for t in tx.xpath(".//w:t") if t.text).strip()
                if box:
                    s.blocks.append(Block(kind=PARAGRAPH, text=box, location=loc, extra={"in": "text box"}))
            if ftype == "shape" and not descr and _local(drawing, "txbxContent") is not None:
                continue  # a plain text box, not an image
            s.blocks.append(Block(kind=FIGURE, figure_type=ftype, name=name, alt_text=descr,
                                  decorative=decorative, location=loc))
    return s
