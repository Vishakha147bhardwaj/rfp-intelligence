from datetime import date

from rfp.ingestion.pipeline import find_doc_date, ingest_folder


def test_doc_date_from_publication_line():
    assert find_doc_date("Publication: 05/29/2024 11:16 AM EDT") == date(2024, 5, 29)


def test_doc_date_from_issue_line():
    assert find_doc_date("First Advertisement Date/Issue Date   26-MAY-2024 08:00:00") == date(2024, 5, 26)


def test_due_date_is_never_the_doc_date():
    assert find_doc_date("The new due date for this RFP will be July 9, 2024 at 2:00 PM CST.") is None


def test_bad_and_unsupported_files_do_not_crash(tmp_path):
    bid = tmp_path / "BidX"
    bid.mkdir()
    (bid / "broken.pdf").write_bytes(b"this is not a pdf")
    (bid / "notes.docx").write_bytes(b"whatever")
    (bid / ".DS_Store").write_bytes(b"")

    docs, report = ingest_folder(bid)

    statuses = {f.file_name: f.status for f in report.files}
    assert docs == []
    assert statuses == {"broken.pdf": "failed", "notes.docx": "skipped"}  # .DS_Store ignored

def test_issue_date_on_line_that_also_has_due_date():
    line = "PORFP Issue Date: | 05/24/2024 | PROPOSAL DUE | 06/10/2024"
    assert find_doc_date(line) == date(2024, 5, 24)