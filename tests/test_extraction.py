from rfp.agents.extraction import finalize_drafts, normalize_value
from rfp.agents.retrieval import RetrievalAgent
from rfp.schemas.agents import FieldDraft, FieldSpec
from rfp.search.engine import SearchResult
from rfp.settings import AgentsConfig

DUE = FieldSpec(
    name="Due Date",
    group="g",
    format="datetime",
    description="d",
    queries=["due date", "closing date"],
)
DOCS = FieldSpec(
    name="Docs", group="g", format="list", description="d", queries=["forms"]
)


def hit(chunk_id: str, page: int = 1) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        bid_id="B1",
        file_name=f"{chunk_id}.pdf",
        page_number=page,
        doc_type="rfp",
        text=f"text of {chunk_id}",
        context_header="[h]",
        score=1.0,
    )


class FakeEngine:
    def __init__(self, results: dict[str, list[SearchResult]]):
        self.results = results

    def search(self, query, top_k=5, bid_id=None, doc_type=None):
        return self.results.get(query, [])[:top_k]


def bundle_for(results):
    agent = RetrievalAgent(
        FakeEngine(results), AgentsConfig(per_query_k=5, per_field_k=5)
    )
    return agent.gather("B1", [DUE, DOCS])


def test_retrieval_fuses_queries_and_dedupes_evidence():
    bundle = bundle_for(
        {
            "due date": [hit("a"), hit("b")],
            "closing date": [hit("b"), hit("c")],
            "forms": [hit("b"), hit("d")],
        }
    )
    assert (
        bundle.by_field["Due Date"][0] == bundle.by_field["Docs"][0]
    )  # chunk b shared, one ID
    assert (
        bundle.get(bundle.by_field["Due Date"][0]).chunk_id == "b"
    )  # b was in both due queries
    assert len(bundle.evidence) == 4 and bundle.queries_run == 3


def test_value_with_valid_citation_keeps_sources():
    bundle = bundle_for({"due date": [hit("a", page=7)]})
    drafts = [
        FieldDraft(
            field="Due Date",
            value="July 9, 2024 2:00 PM CST",
            evidence_ids=["E1"],
            confidence=0.95,
            reasoning="Addendum 2",
        )
    ]
    result = finalize_drafts([DUE], drafts, bundle)["Due Date"]
    assert result.value == "July 9, 2024 2:00 PM CST"
    assert (result.sources[0].file, result.sources[0].page) == ("a.pdf", 7)


def test_invented_citation_is_rejected():
    bundle = bundle_for({"due date": [hit("a")]})
    drafts = [
        FieldDraft(
            field="Due Date",
            value="June 1",
            evidence_ids=["E99"],
            confidence=0.9,
            reasoning="?",
        )
    ]
    result = finalize_drafts([DUE], drafts, bundle)["Due Date"]
    assert result.value is None and result.sources == [] and "Rejected" in result.notes


def test_missing_field_becomes_not_found():
    result = finalize_drafts([DUE, DOCS], [], bundle_for({}))
    assert result["Docs"].value is None and "Not found" in result["Docs"].notes


def test_placeholders_and_shapes_are_normalized():
    assert normalize_value("N/A", DUE) is None
    assert normalize_value("W9 form", DOCS) == ["W9 form"]
    assert normalize_value(["W9", "  ", "Not specified"], DOCS) == ["W9"]
    assert normalize_value(["a", "b"], DUE) == "a; b"


def test_neighbor_expansion_adds_adjacent_chunk():
    seed = SearchResult(
        chunk_id="c0",
        bid_id="B1",
        file_name="specs.pdf",
        page_number=1,
        doc_type="specs",
        text="SKU table part 1",
        context_header="[h]",
        score=1.0,
        chunk_index=0,
    )
    tail = {
        "chunk_id": "c1",
        "bid_id": "B1",
        "file_name": "specs.pdf",
        "page_number": 1,
        "doc_type": "specs",
        "addendum_number": None,
        "section": None,
        "text": "340-DMMK table part 2",
        "context_header": "[h]",
        "chunk_index": 1,
    }
    fetched = []

    def fake_fetch(bid_id, file_name, indexes):
        fetched.append((file_name, indexes))
        return [tail] if 1 in indexes else []

    spec = FieldSpec(
        name="Part_no",
        group="g",
        format="list",
        description="d",
        queries=["sku"],
        expand_neighbors=True,
    )
    agent = RetrievalAgent(
        FakeEngine({"sku": [seed]}), AgentsConfig(), fetch_chunks=fake_fetch
    )
    bundle = agent.gather("B1", [spec])

    assert fetched == [("specs.pdf", [1])]  # asked for the next chunk
    assert [e.chunk_id for e in bundle.evidence] == ["c0", "c1"]
    assert "340-DMMK" in bundle.evidence[1].text and bundle.neighbors_added == 1


def test_id_patterns_add_missing_skus_but_not_phone_fragments():
    spec = FieldSpec(
        name="Part_no",
        group="g",
        format="list",
        description="d",
        queries=["sku"],
        id_patterns=[r"(?<![\w-])\d{3}-[A-Z0-9]{4}(?![\w-])"],
    )
    head = SearchResult(
        chunk_id="c0",
        bid_id="B1",
        file_name="specs.pdf",
        page_number=1,
        doc_type="specs",
        text="Base   210-BLYZ\nCPU   379-BFNZ",
        context_header="[h]",
        score=1.0,
    )
    tail = SearchResult(
        chunk_id="c1",
        bid_id="B1",
        file_name="specs.pdf",
        page_number=1,
        doc_type="specs",
        text="Software   340-DMMK\nCall 410-260-7533",
        context_header="[h]",
        score=0.5,
    )
    agent = RetrievalAgent(FakeEngine({"sku": [head, tail]}), AgentsConfig())
    bundle = agent.gather("B1", [spec])

    drafts = [
        FieldDraft(
            field="Part_no",
            value=["210-BLYZ", "210-BLYZ"],
            evidence_ids=["E1"],
            confidence=0.9,
            reasoning="from the table",
        )
    ]
    result = finalize_drafts([spec], drafts, bundle)["Part_no"]

    assert result.value == [
        "210-BLYZ",
        "379-BFNZ",
        "340-DMMK",
    ]  # deduped, completed, in order
    assert "260-7533" not in result.value  # phone fragment not a SKU
    assert len(result.sources) == 2  # tail chunk is now cited
    assert "Pattern check added 2" in result.notes
