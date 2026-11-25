"""Reading source material (a paper, notes, a protocol) from uploaded files."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

MAX_SOURCE_CHARS = 24000
MAX_PDF_PAGES = 60
MAX_UNZIPPED = 40 * 1024 * 1024

TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".tex", ".csv", ".tsv", ".json", ".rst", ".bib")


class SourceError(ValueError):
    """The file could not be read as text; the message is for the user."""


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            info = zf.getinfo("word/document.xml")
            if info.file_size > MAX_UNZIPPED:
                raise SourceError("The Word file is too large to read.")
            xml = zf.read(info)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise SourceError("This does not look like a .docx file.") from exc
    if b"<!ENTITY" in xml:
        raise SourceError("The Word file contains XML entities and was not read.")
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ET.fromstring(xml)
    lines = []
    for para in root.iter(f"{ns}p"):
        chunks = []
        for el in para.iter():
            if el.tag == f"{ns}t" and el.text:
                chunks.append(el.text)
            elif el.tag in (f"{ns}tab",):
                chunks.append("\t")
            elif el.tag in (f"{ns}br", f"{ns}cr"):
                chunks.append("\n")
        lines.append("".join(chunks))
    return "\n".join(lines)


def _pdf_text(data: bytes, notes: list[str]) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise SourceError("Reading PDF needs the 'pypdf' package: pip install pypdf") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - any failure means we cannot read it
                raise SourceError("The PDF is password-protected.") from exc
        pages = reader.pages
        total = len(pages)
        out = []
        for i in range(min(total, MAX_PDF_PAGES)):
            try:
                out.append(pages[i].extract_text() or "")
            except Exception:  # noqa: BLE001 - one bad page should not lose the document
                out.append("")
    except PdfReadError as exc:
        raise SourceError(f"The PDF could not be read ({exc}).") from exc
    except SourceError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf raises many types on damaged files
        raise SourceError(f"The PDF could not be read ({type(exc).__name__}).") from exc
    if total > MAX_PDF_PAGES:
        notes.append(f"The PDF has {total} pages; only the first {MAX_PDF_PAGES} were read.")
    text = "\n\n".join(out)
    if len(re.sub(r"\s", "", text)) < 40 * min(total, MAX_PDF_PAGES):
        notes.append("Very little text was found. If this is a scanned PDF it has no text layer; paste the text instead.")
    return text


def extract_text(filename: str, data: bytes) -> tuple[str, list[str]]:
    """Return ``(text, notes)`` for an uploaded document."""
    name = (filename or "").lower()
    notes: list[str] = []
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        text = _pdf_text(data, notes)
    elif name.endswith(".docx"):
        text = _docx_text(data)
    elif name.endswith(TEXT_SUFFIXES) or not name:
        text = _decode(data)
    elif name.endswith(".doc"):
        raise SourceError("Old .doc files are not supported; save the document as .docx or PDF.")
    else:
        raise SourceError("Unsupported file type. Use PDF, DOCX, Markdown, LaTeX or plain text.")
    text = re.sub(r"[ \t]+\n", "\n", text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", ""))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, notes


def clip_source(text: str, limit: int = MAX_SOURCE_CHARS) -> tuple[str, str]:
    """Shorten very long source text, saying so. Keeps the beginning and the end."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text, ""
    head, tail = int(limit * 0.7), int(limit * 0.3)
    omitted = len(text) - head - tail
    clipped = f"{text[:head]}\n\n[... {omitted} characters omitted ...]\n\n{text[-tail:]}"
    return clipped, f"The source is {len(text):,} characters long; the model saw the first {head:,} and the last {tail:,}."
