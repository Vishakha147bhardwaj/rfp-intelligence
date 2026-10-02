from rfp.agents.qa import AnswerDraft, NOT_FOUND, finalize_answer, resolve_bids,change_sentences

EVIDENCE = [
    {"bid_id": "Bid1", "file_name": "Addendum 2.pdf", "page_number": 1,
     "text": "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."},
    {"bid_id": "Bid1", "file_name": "RFP.pdf", "page_number": 2, "text": "Solicitation Due 27-JUN-2024"},
]


def test_valid_citations_are_kept():
    draft = AnswerDraft(found=True, answer="The deadline is July 9, 2024 at 2:00 PM CST [1], "
                                            "extended from June 27 [2].")
    text, citations, found = finalize_answer(draft, EVIDENCE)
    assert found and [c.n for c in citations] == [1, 2]
    assert citations[0].file == "Addendum 2.pdf" and "[1]" in text


def test_invented_citation_is_removed():
    draft = AnswerDraft(found=True, answer="Deadline is July 9 [1] per the portal [7].")
    text, citations, _ = finalize_answer(draft, EVIDENCE)
    assert "[7]" not in text and [c.n for c in citations] == [1]


def test_answer_without_valid_citation_becomes_not_found():
    draft = AnswerDraft(found=True, answer="The deadline is probably in July [9].")
    assert finalize_answer(draft, EVIDENCE) == (NOT_FOUND, [], False)


def test_unknown_bids_fall_back_to_all():
    assert resolve_bids(["Bid2", "Bid9"], ["Bid1", "Bid2"]) == ["Bid2"]
    assert resolve_bids(["dell"], ["Bid1", "Bid2"]) == ["Bid1", "Bid2"]

def test_change_sentences_turn_addendum_text_into_original_style_queries():
    addendum = ("ADDENDUM No. 2 RFP JA-207652 Student and Staff Computing Devices. "
                "The Purpose of this Addendum is to extend the due date of this RFP. "
                "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST. "
                "The information in this Addendum is hereby incorporated.")
    queries = change_sentences(addendum)
    assert "The due date for this RFP will be July 9, 2024 at 2:00 PM CST." in queries
    assert all("incorporated" not in q for q in queries)        # no change cue -> not a query