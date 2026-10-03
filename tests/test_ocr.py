import pymupdf

from rfp.ingestion import pdf_parser
from rfp.ingestion.ocr import ocr_lines


def blank_pdf(tmp_path):
    path = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path


def test_ocr_boxes_are_put_in_reading_order():
    boxes = [
        ([[100, 10], [200, 10], [200, 30], [100, 30]], "World", 0.9),
        ([[10, 12], [90, 12], [90, 28], [10, 28]], "Hello", 0.9),
        ([[10, 50], [90, 50], [90, 70], [10, 70]], "Next line", 0.9),
    ]
    assert ocr_lines(boxes) == "Hello World\nNext line"


def test_page_without_text_is_ocred(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pdf_parser, "ocr_page", lambda page, dpi: "SIGNED FORM text from an image"
    )
    pages, errors = pdf_parser.parse_pdf(blank_pdf(tmp_path))
    assert errors == []
    assert pages[0].text == "SIGNED FORM text from an image"
    assert pages[0].ocr_used and not pages[0].is_empty


def test_failed_ocr_keeps_page_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_parser, "ocr_page", lambda page, dpi: "")
    pages, _ = pdf_parser.parse_pdf(blank_pdf(tmp_path))
    assert pages[0].is_empty and not pages[0].ocr_used
