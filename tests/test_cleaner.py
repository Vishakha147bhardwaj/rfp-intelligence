from rfp.ingestion.cleaner import clean_pages, clean_text
from rfp.schemas.documents import Page


def _pages(*texts):
    return [Page(page_number=i + 1, text=t) for i, t in enumerate(texts)]


def test_repeated_header_and_footer_removed():
    pages = _pages(
        "Request For Proposal 168884 JA-207652\nDallas ISD rev 2.0 Page 2 of 40\nWarranty: 1 year",
        "Request For Proposal 168884 JA-207652\nDallas ISD rev 2.0 Page 3 of 40\nDelivery in 30 days",
        "Request For Proposal 168884 JA-207652\nDallas ISD rev 2.0 Page 4 of 40\nNet 30 payment",
    )
    cleaned, removed = clean_pages(pages)
    assert [p.text for p in cleaned] == [
        "Warranty: 1 year",
        "Delivery in 30 days",
        "Net 30 payment",
    ]
    assert len(removed) == 2


def test_page_label_line_removed():
    cleaned, _ = clean_pages(_pages("Page 1 | 1\nADDENDUM No. 2"))
    assert cleaned[0].text == "ADDENDUM No. 2"


def test_hyphen_break_keeps_hyphen():
    assert (
        clean_text("attend the pre-\nproposal meeting")
        == "attend the pre-proposal meeting"
    )


def test_wrapped_sentence_is_joined():
    assert (
        clean_text("The term shall be three\nyears with renewals.")
        == "The term shall be three years with renewals."
    )


def test_column_rows_are_not_joined():
    text = "Dell Latitude 5550 XCTO Base   210-BLYZ\nintel vPro Management Disabled   631-BBSQ"
    assert clean_text(text) == text


def test_list_items_are_not_joined():
    assert (
        clean_text("Requirements\n- warranty 3 years")
        == "Requirements\n- warranty 3 years"
    )


def test_inline_bullets_split_onto_lines():
    text = "Requirements • Memory: 16GB • Storage: 256GB SSD"
    assert clean_text(text) == "Requirements\n• Memory: 16GB\n• Storage: 256GB SSD"
