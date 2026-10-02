import pytest

from rfp.ingestion.detector import detect_doc_type
from rfp.schemas.documents import DocType


@pytest.mark.parametrize(
    "file_name, file_type, head, expected_type, expected_num",
    [
        ("Bid Information _ BidNet Direct.html", "html", "", DocType.BID_PAGE, None),
        ("Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf", "pdf", "", DocType.ADDENDUM, 2),
        ("Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf", "pdf", "", DocType.ADDENDUM, 1),
        ("Contract_Affidavit.pdf", "pdf", "", DocType.AFFIDAVIT, None),
        ("Dell_Laptop_Specs.pdf", "pdf", "", DocType.SPECS, None),
        ("PORFP_-_Dell_Laptop_Final.pdf", "pdf", "", DocType.RFP, None),
        # name says nothing -> falls back to the title text
        ("JA-207652 Student and Staff Computing Devices FINAL.pdf", "pdf",
         "REQUEST FOR PROPOSAL JA-207652", DocType.RFP, None),
        ("scan_001.pdf", "pdf", "ADDENDUM NO. 3 to RFP 12345", DocType.ADDENDUM, 3),
        ("random.pdf", "pdf", "hello world", DocType.OTHER, None),
    ],
)
def test_detect_doc_type(file_name, file_type, head, expected_type, expected_num):
    result = detect_doc_type(file_name, file_type, head)
    assert result.doc_type == expected_type
    assert result.addendum_number == expected_num