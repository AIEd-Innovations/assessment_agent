"""Turn uploaded instructor files (text, PDF, Word, Jupyter) into the text the grader reads."""
from __future__ import annotations

import io
import json
from pathlib import PurePosixPath

CONVERTED = {".pdf", ".docx", ".ipynb"}


class UnsupportedFileError(ValueError):
    pass


def text_name(filename: str) -> str:
    """Name of the text file stored for an upload: converted files get a .txt suffix."""
    return f"{filename}.txt" if PurePosixPath(filename).suffix.lower() in CONVERTED else filename


def extract_text(filename: str, data: bytes) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".pdf":
        text = _pdf(data)
        if not text.strip():
            raise UnsupportedFileError(f"{filename} has no extractable text (is it a scanned PDF?)")
        return text
    if suffix == ".docx":
        return _docx(data)
    if suffix == ".ipynb":
        return _notebook(data)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise UnsupportedFileError(
            f"{filename} is not a supported file (UTF-8 text, PDF, Word .docx or Jupyter .ipynb)"
        )


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise UnsupportedFileError(f"could not read the PDF: {exc}") from exc


def _docx(data: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedFileError(f"could not read the Word document: {exc}") from exc
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        lines += [" | ".join(cell.text for cell in row.cells) for row in table.rows]
    return "\n".join(lines)


def _notebook(data: bytes) -> str:
    """Code and markdown cells only; outputs are dropped."""
    try:
        cells = json.loads(data.decode("utf-8"))["cells"]
    except (ValueError, KeyError, UnicodeDecodeError) as exc:
        raise UnsupportedFileError(f"could not read the notebook: {exc}") from exc
    parts = []
    for cell in cells:
        source = cell.get("source", "")
        parts.append("".join(source) if isinstance(source, list) else str(source))
    return "\n\n".join(parts)
