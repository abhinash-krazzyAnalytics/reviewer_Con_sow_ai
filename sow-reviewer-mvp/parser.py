"""Parse an SOW file (.pdf / .docx / .md) into Markdown + heading sections.

Docling is the primary parser. If Docling is not installed (or fails), a simpler
fallback is used (pypdf for PDF, python-docx for DOCX) and a warning is recorded.
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*$", re.M)
MIN_HEADINGS = 3


@dataclass
class ParsedSOW:
    markdown: str
    sections: list            # [{"title": str, "text": str}]
    parser_used: str          # docling | fallback-pypdf | fallback-docx | plain-text
    section_fallback: bool    # True when fewer than MIN_HEADINGS headings were found
    warnings: list = field(default_factory=list)


def _docling_markdown(path: Path) -> str:
    from docling.document_converter import DocumentConverter
    result = DocumentConverter().convert(str(path))
    return result.document.export_to_markdown()


def _pdf_fallback(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)


def _docx_fallback(path: Path) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    out = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[1]
        if tag == "p":
            p = Paragraph(child, doc)
            text = p.text.strip()
            if not text:
                continue
            style = p.style.name or ""
            m = re.match(r"Heading (\d)", style)
            if m:
                out.append("#" * int(m.group(1)) + " " + text)
            elif style == "Title":
                out.append("# " + text)
            elif "List" in style:
                out.append("- " + text)
            else:
                out.append(text)
        elif tag == "tbl":
            table = Table(child, doc)
            rows = [[c.text.strip().replace("\n", " ") for c in r.cells] for r in table.rows]
            if not rows:
                continue
            lines = ["| " + " | ".join(rows[0]) + " |",
                     "|" + "|".join(["---"] * len(rows[0])) + "|"]
            lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
            out.append("\n".join(lines))
    return "\n\n".join(out)


def split_sections(markdown: str):
    """Split on # / ## headings. Returns (sections, used_full_document_fallback)."""
    matches = list(HEADING_RE.finditer(markdown))
    if len(matches) < MIN_HEADINGS:
        return [{"title": "FULL DOCUMENT", "text": markdown}], True
    sections = []
    if matches[0].start() > 0 and markdown[:matches[0].start()].strip():
        sections.append({"title": "PREAMBLE", "text": markdown[:matches[0].start()].strip()})
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        sections.append({"title": m.group(2).strip(), "text": markdown[m.end():end].strip()})
    return sections, False


def parse_document(path) -> ParsedSOW:
    path = Path(path)
    ext = path.suffix.lower()
    warnings = []

    if ext in (".md", ".txt"):
        md, used = path.read_text(encoding="utf-8"), "plain-text"
    elif ext in (".pdf", ".docx"):
        md, used = None, None
        if os.getenv("SOW_PARSER", "docling") != "fallback":
            try:
                md, used = _docling_markdown(path), "docling"
            except ImportError:
                warnings.append("Docling is not installed; used the simpler fallback parser.")
            except Exception as e:  # Docling failed on this file
                warnings.append(f"Docling failed ({type(e).__name__}); used the fallback parser.")
        if md is None:
            if ext == ".pdf":
                md, used = _pdf_fallback(path), "fallback-pypdf"
                warnings.append("Fallback PDF text has no heading structure and tables may be scrambled.")
            else:
                md, used = _docx_fallback(path), "fallback-docx"
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use .pdf, .docx or .md")

    if not md.strip():
        raise ValueError("No text could be extracted from the document (scanned PDF?).")

    sections, fallback = split_sections(md)
    if fallback:
        warnings.append("Fewer than 3 headings detected; the whole document is treated as one section.")
    return ParsedSOW(md, sections, used, fallback, warnings)
