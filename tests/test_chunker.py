from rfp.schemas.documents import DocType, Page, ParsedDocument, Table
from rfp.search.chunker import SENTENCE_SPLIT, chunk_document, detect_heading
from rfp.settings import ChunkingConfig

SMALL = ChunkingConfig(
    target_tokens=50, max_tokens=70, min_tokens=10, overlap_tokens=15
)


def make_doc(*page_texts, tables=None, addendum=None):
    pages = [Page(page_number=i + 1, text=t) for i, t in enumerate(page_texts)]
    if tables:
        pages[0].tables = tables
    return ParsedDocument(
        bid_id="B1",
        file_name="Addendum 2 RFP.pdf",
        file_path="x",
        file_hash="h",
        file_type="pdf",
        doc_type=DocType.ADDENDUM if addendum else DocType.RFP,
        addendum_number=addendum,
        pages=pages,
    )


def test_heading_patterns():
    assert detect_heading("1.2 Terms", set()) == "1.2 Terms"
    assert detect_heading("## Dates", set()) == "Dates"
    assert detect_heading("LENGTH OF CONTRACT", set()) == "LENGTH OF CONTRACT"
    assert (
        detect_heading(
            "PURPOSE OF REQUEST FOR PROPOSAL (RFP) This Request is for laptops.", set()
        )
        == "PURPOSE OF REQUEST FOR PROPOSAL (RFP)"
    )
    assert detect_heading("Delivery within 45 days of award.", set()) is None
    assert detect_heading("NTSC, FHD Cam", set()) is None
    assert (
        detect_heading("Section 2 – Agency Point of Contact (POC) Information", set())
        == "Section 2 – Agency Point of Contact (POC) Information"
    )
    assert detect_heading("16 GB: 2 x 8 GB, DDR5, 5600 MT/s   370-BBTL", set()) is None


def test_sections_split_when_big_enough():
    cfg = ChunkingConfig(
        target_tokens=50, max_tokens=70, min_tokens=0, overlap_tokens=15
    )
    chunks = chunk_document(
        make_doc("1.1 General Information\nDue date is June 1.\n\n1.2 Terms\nNet 30."),
        cfg,
    )
    assert [c.section for c in chunks] == ["1.1 General Information", "1.2 Terms"]


def test_tiny_sections_merge():
    cfg = ChunkingConfig(
        target_tokens=50, max_tokens=70, min_tokens=80, overlap_tokens=15
    )
    chunks = chunk_document(
        make_doc("1.1 General Information\nDue June 1.\n\n1.2 Terms\nNet 30."), cfg
    )
    assert len(chunks) == 1


def test_chunks_never_cross_pages():
    chunks = chunk_document(make_doc("Page one text.", "Page two text."), SMALL)
    assert [c.page_number for c in chunks] == [1, 2]


def test_long_text_respects_max_and_overlaps():
    sentences = [
        f"Sentence {i} covers delivery terms and warranty coverage." for i in range(20)
    ]
    chunks = chunk_document(make_doc(" ".join(sentences)), SMALL)
    assert len(chunks) > 2
    assert all(c.n_tokens <= SMALL.max_tokens for c in chunks)
    last_sentence = SENTENCE_SPLIT.split(chunks[0].text)[-1]
    assert chunks[1].text.startswith(last_sentence)


def test_big_table_repeats_header():
    rows = "\n".join(f"| item {i} | 16 GB DDR5 memory module |" for i in range(40))
    table = Table(
        page_number=1,
        markdown=f"| Item | Spec |\n|---|---|\n{rows}",
        n_rows=41,
        n_cols=2,
    )
    chunks = [
        c
        for c in chunk_document(make_doc("Specs follow.", tables=[table]), SMALL)
        if c.is_table
    ]
    assert len(chunks) > 1
    assert all(c.text.startswith("| Item | Spec |\n|---|---|") for c in chunks)


def test_context_header_and_stable_ids():
    doc = make_doc("ADDENDUM No. 2\nThe new due date is July 9, 2024.", addendum=2)
    first, second = chunk_document(doc, SMALL), chunk_document(doc, SMALL)
    assert (
        "Bid: B1" in first[0].context_header
        and "addendum #2" in first[0].context_header
    )
    assert "Page 1" in first[0].context_header
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
