import json

import pytest

from assessment_agent.extract import UnsupportedFileError, extract_text, text_name


def test_text_files_pass_through_under_their_own_name():
    assert extract_text("Sort.java", "class Sort {}".encode()) == "class Sort {}"
    assert text_name("Sort.java") == "Sort.java"


def test_pdf_text_is_extracted(make_pdf):
    assert "pointers" in extract_text("notes.pdf", make_pdf("Linked lists use pointers"))
    assert text_name("notes.pdf") == "notes.pdf.txt"


def test_pdf_without_text_is_rejected(make_pdf):
    with pytest.raises(UnsupportedFileError, match="no extractable text"):
        extract_text("scan.pdf", make_pdf(""))


def test_broken_pdf_is_rejected():
    with pytest.raises(UnsupportedFileError, match="could not read the PDF"):
        extract_text("broken.pdf", b"%PDF-1.4 not really")


def test_docx_paragraphs_are_extracted(make_docx):
    assert extract_text("key.docx", make_docx("Q1: O(n)", "Q2: a stack")) == "Q1: O(n)\nQ2: a stack"


def test_notebook_keeps_cells_and_drops_outputs():
    notebook = {"cells": [
        {"cell_type": "markdown", "source": ["# Lab 4\n", "Sorting"]},
        {"cell_type": "code", "source": "print(sorted(x))", "outputs": [{"text": "SECRET OUTPUT"}]},
    ]}
    text = extract_text("lab.ipynb", json.dumps(notebook).encode())
    assert "# Lab 4\nSorting" in text
    assert "print(sorted(x))" in text
    assert "SECRET OUTPUT" not in text


def test_binary_files_are_rejected():
    with pytest.raises(UnsupportedFileError, match="not a supported file"):
        extract_text("diagram.png", b"\x89PNG\r\n\x1a\n\xff\xfe")
