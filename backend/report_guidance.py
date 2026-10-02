"""
Plain-language guidance for every accessibility issue the checks can raise, used by the admin report.

Written for the people who have to FIX documents (clerks, communications staff), not for developers: what the
problem means for a real reader, and how to fix it in the tools they actually use. A test keeps this catalogue
complete: adding a new check without adding its guidance here fails the build.
"""

from typing import Dict

WCAG_NAMES: Dict[str, str] = {
    "1.1.1": "Non-text Content",
    "1.3.1": "Info and Relationships",
    "1.3.2": "Meaningful Sequence",
    "1.4.5": "Images of Text",
    "2.4.2": "Page Titled",
    "3.1.1": "Language of Page",
}

# code -> (short title, why it matters to a reader, how to fix it)
GUIDANCE: Dict[str, tuple] = {
    "DOC_TITLE_MISSING": (
        "Document has no title",
        "Screen readers, browser tabs and search results show the title; without one people hear or see the file name instead.",
        "Word/PowerPoint: File > Info > Properties > Title. Use a short descriptive title, not the file name."),
    "DOC_LANGUAGE_MISSING": (
        "Document language not set",
        "A screen reader needs to know the language to pronounce words correctly; the wrong voice makes text unintelligible.",
        "Word: Review > Language > Set Proofing Language. PowerPoint: Review > Language. Pick the document's main language."),
    "FIG_ALT_MISSING": (
        "Image has no alternative text",
        "A blind reader is told only 'image' and misses the information; sighted readers on slow or text-only connections miss it too.",
        "Right-click the image > View/Edit Alt Text and describe what it shows and why it is there. Mark purely decorative images as decorative."),
    "FIG_ALT_PLACEHOLDER": (
        "Alternative text is a file name or placeholder",
        "The reader hears something like 'image1 dot png', which tells them nothing.",
        "Replace it with a real description of the image's content and purpose."),
    "FIG_ALT_LONG": (
        "Alternative text is very long",
        "Long alt text is tiring to listen to and often means the image holds information that belongs in the page text.",
        "Keep alt text to a sentence or two and put the detailed description in the document text nearby."),
    "FIG_ALT_REDUNDANT": (
        "Alternative text starts with 'image of' or 'picture of'",
        "Screen readers already announce 'image', so the reader hears it twice.",
        "Delete the leading 'Image of' and start with the description."),
    "TABLE_DESCRIPTION_MISSING": (
        "Table has no description",
        "Tables are hard to listen to cell by cell; a short description tells the reader what the table contains and whether to explore it.",
        "Word: right-click the table > Table Properties > Alt Text. PowerPoint: right-click the table > View Alt Text. Summarise what the table shows."),
    "TABLE_DESCRIPTION_PLACEHOLDER": (
        "Table description is a placeholder",
        "A placeholder gives the reader nothing to go on.",
        "Replace it with a sentence describing what the table shows."),
    "TABLE_NO_HEADER": (
        "Table has no header row",
        "Without marked header cells a screen reader cannot tell the reader which column or row each value belongs to.",
        "Word: select the table > Table Design > tick Header Row, and Layout > Repeat Header Rows. PDF: tag the first row's cells as headers (TH)."),
    "TABLE_MERGED_CELLS": (
        "Table has merged or split cells",
        "Many screen readers lose their place in tables with merged cells.",
        "Restructure into a simple grid where possible, or split it into several simple tables."),
    "TABLE_EMPTY_ROW": (
        "Table has an empty row",
        "Empty rows are announced as 'blank' and are sometimes mistaken for the end of the table.",
        "Delete the empty row; use spacing or paragraph formatting for visual gaps."),
    "HEADING_SKIP": (
        "Heading levels skip (for example Heading 1 straight to Heading 3)",
        "Readers navigate by heading level; a skipped level makes it look as if a section is missing.",
        "Change the heading to the next level down, using the built-in Heading styles (not just bold or large text)."),
    "NO_HEADINGS": (
        "Long document has no headings",
        "Without headings a screen-reader user cannot jump to a section and must listen from the start.",
        "Apply the built-in Heading 1/2/3 styles to section titles."),
    "SLIDE_TITLE_MISSING": (
        "Slide has no title",
        "Slide titles are how people find and move between slides; an untitled slide is announced only as 'slide 4'.",
        "Give every slide a title in its title placeholder. If you don't want it visible, keep it and move it off the slide edge."),
    "SLIDE_TITLE_DUPLICATE": (
        "Two slides share the same title",
        "A reader choosing from a list of slides cannot tell them apart.",
        "Make each title unique, for example 'Budget (continued)' or add what differs."),
    "SLIDE_TITLE_NOT_FIRST": (
        "Slide title is not read first",
        "A screen reader reads slide content in layer order, so the reader hears the body before they know what the slide is about.",
        "PowerPoint: Home > Arrange > Selection Pane, and move the title to the bottom of the list (it is read first)."),
    "SLIDE_READING_ORDER": (
        "Slide reading order may not match how it looks",
        "Content may be read in a confusing order. (This check is a low-confidence hint.)",
        "PowerPoint: Home > Arrange > Selection Pane, and put items in the order a reader should hear them (bottom of the list is read first)."),
    "SLIDE_HIDDEN": (
        "Slide is hidden",
        "Hidden slides are skipped when presenting but are still read by some assistive technology, which can confuse readers.",
        "Delete the slide if it is not needed, or unhide it."),
    "PDF_NO_TEXT": (
        "PDF is a scan with no text",
        "A scanned page is just a picture: a screen reader has nothing to read, and the text cannot be searched or enlarged cleanly.",
        "Run OCR (Acrobat: Scan & OCR > Recognize Text), then proof-read the result. Better: re-create the PDF from the original document."),
    "PDF_PAGES_WITHOUT_TEXT": (
        "Some PDF pages are images with no text",
        "Those pages are silent to a screen reader.",
        "Run OCR on those pages (Acrobat: Scan & OCR > Recognize Text) and proof-read them."),
    "PDF_TEXT_LAYER_UNRELIABLE": (
        "PDF's hidden text does not match what is on the pages",
        "This PDF is a scan whose hidden text layer is wrong (often bad OCR). A screen reader would read the wrong words.",
        "Re-run OCR on the whole document and proof-read, or re-create the PDF from the original."),
    "PDF_TEXT_LAYER_GARBLED": (
        "PDF text is unreadable (unmapped or garbage characters)",
        "The PDF's fonts cannot be translated to text, so a screen reader reads gibberish or nothing.",
        "Re-export the PDF from the original document with fonts embedded, or run OCR on the affected pages."),
    "OCR_LOW_CONFIDENCE": (
        "OCR was unsure about some pages",
        "Poor scans lead to wrong words in the recovered text.",
        "Have someone read the flagged pages against the originals; re-scan at a higher quality if possible."),
    "PDF_UNTAGGED": (
        "PDF is not tagged",
        "Tags give a PDF its headings, lists, tables and reading order. An untagged PDF is read as one undifferentiated stream, if at all.",
        "Best: export again from Word/PowerPoint with 'Create tagged PDF' (or 'Document structure tags for accessibility') ticked. Otherwise Acrobat > Accessibility > Autotag, then check the Tags panel."),
    "PDF_LANGUAGE_MISSING": (
        "PDF language not set",
        "A screen reader needs the language to choose the right voice.",
        "Acrobat: File > Properties > Advanced > Language. Or set the language in the source document and export again."),
    "PDF_TITLE_MISSING": (
        "PDF has no title",
        "The title is what appears in the browser tab and is announced by screen readers.",
        "Acrobat: File > Properties > Description > Title. Or set the title in the source document and export again."),
    "PDF_DISPLAY_TITLE": (
        "PDF window title shows the file name",
        "The title bar shows something like 'scan_0042.pdf' instead of the real title.",
        "Acrobat: File > Properties > Initial View > Show: Document Title."),
    "PDF_GENERIC_HEADING": (
        "Headings use the generic 'H' tag",
        "Without H1-H6 levels a reader cannot tell main headings from sub-headings.",
        "Acrobat Tags panel: change each H to the right level (H1, H2, ...), or fix the styles in the source document and export again."),
    "PDF_FIRST_HEADING_NOT_H1": (
        "First heading is not a level 1",
        "The document outline starts in the middle, which is confusing.",
        "Make the document's main title Heading 1 in the source document and export again."),
    "PDF_NONSTANDARD_TAG": (
        "PDF uses custom tags with no standard meaning",
        "Assistive technology does not know what a custom tag is, so it may skip or mis-announce that content.",
        "Map the custom tags to standard ones (Acrobat: Tags panel > Role Map) or re-export from the source document."),
    "PDF_UNTAGGED_CONTENT": (
        "Some PDF text is not in the tag structure",
        "Text outside the tags can be skipped entirely by a screen reader.",
        "Acrobat > Accessibility > Reading Order, or fix and re-export from the source document."),
    "PDF_TAG_TREE_NOT_INSPECTED": (
        "PDF tags could not be checked",
        "The file is tagged but its tags could not be read automatically, so figures and tables were not checked.",
        "Check this file manually in Acrobat (Accessibility > Full Check)."),
}


def describe(code: str) -> dict:
    title, why, how = GUIDANCE.get(code, (code.replace("_", " ").capitalize(), "", ""))
    return {"title": title, "why": why, "how": how}
