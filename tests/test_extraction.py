from rfp.agents.extraction import finalize_drafts, normalize_value
from rfp.agents.retrieval import RetrievalAgent
from rfp.schemas.agents import FieldDraft, FieldSpec
from rfp.search.engine import SearchResult
from rfp.settings import AgentsConfig

DUE = FieldSpec(name="Due Date", group="g", format="datetime", description="d", queries=["due date", "closing date"])
DOCS = FieldSpec(name="Docs", group="g", format="list", description="d", queries=["forms"])


def hit(chunk_id: str, page: int = 1) -> SearchResult:
    return SearchResult(chunk_id=chunk_id, bid_id="B1", file_name=f"{chunk_id}.pdf", page_number=page,
                        doc_type="rfp", text=f"text of {chunk_id}", context_header="[h]", score=1.0)


class FakeEngine:
    def __init__(self, results: dict[str, list[SearchResult]]):
        self.results = results

    def search(self, query, top_k=5, bid_id=None):
        return self.results.get(query, [])[:top_k]


def bundle_for(results):
    agent = RetrievalAgent(FakeEngine(results), AgentsConfig(per_query_k=5, per_field_k=5))
    return agent.gather("B1", [DUE, DOCS])


def test_retrieval_fuses_queries_and_dedupes_evidence():
    bundle = bundle_for({
        "due date": [hit("a"), hit("b")],
        "closing date": [hit("b"), hit("c")],
        "forms": [hit("b"), hit("d")],
    })
    assert bundle.by_field["Due Date"][0] == bundle.by_field["Docs"][0]   # chunk b shared, one ID
    assert bundle.get(bundle.by_field["Due Date"][0]).chunk_id == "b"     # b was in both due queries
    assert len(bundle.evidence) == 4 and bundle.queries_run == 3


def test_value_with_valid_citation_keeps_sources():
    bundle = bundle_for({"due date": [hit("a", page=7)]})
    drafts = [FieldDraft(field="Due Date", value="July 9, 2024 2:00 PM CST", evidence_ids=["E1"],
                         confidence=0.95, reasoning="Addendum 2")]
    result = finalize_drafts([DUE], drafts, bundle)["Due Date"]
    assert result.value == "July 9, 2024 2:00 PM CST"
    assert (result.sources[0].file, result.sources[0].page) == ("a.pdf", 7)


def test_invented_citation_is_rejected():
    bundle = bundle_for({"due date": [hit("a")]})
    drafts = [FieldDraft(field="Due Date", value="June 1", evidence_ids=["E99"], confidence=0.9, reasoning="?")]
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