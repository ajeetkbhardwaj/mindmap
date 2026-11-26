import pytest
from map.retrieval.hybrid import HybridRetriever, RetrievalOptions

class MockGraph:
    def query(self, cypher, params):
        if "toLower(n.name) CONTAINS" in cypher:
            return [{"n": {"name": "find_user", "path": "auth.py"}, "type": ["Function"]}]
        return []

@pytest.mark.asyncio
async def test_hybrid_retriever_ranking():
    retriever = HybridRetriever(rag=None)
    mock_graph = MockGraph()
    opts = RetrievalOptions(exact_symbol=True, graph_traversal=False, full_text=False, deepwiki_rag=False)
    results = await retriever.retrieve(mock_graph, "user", "proj", opts)
    assert len(results) == 1
    assert results[0]["source"] == "graph_exact"
    assert results[0]["score"] == 1.0

