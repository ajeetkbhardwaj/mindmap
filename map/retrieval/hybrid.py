import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from map.graph import GraphService


@dataclass
class RetrievalOptions:
    exact_symbol: bool = True
    graph_traversal: bool = True
    full_text: bool = True
    deepwiki_rag: bool = True
    limit: int = 20


@dataclass
class RetrievalResult:
    items: list[dict]
    source: str


_SOURCE_SCORE = {
    "graph_exact": 1.0,
    "graph_traversal": 0.8,
    "graph_fulltext": 0.6,
    "deepwiki_rag": 0.4,
}


class HybridRetriever:
    """Graph-first multi-stage retrieval. Merges and ranks results across stages."""

    def __init__(self, rag=None):
        self._rag = rag

    def _get_rag(self):
        if self._rag is None:
            try:
                from mind.api.rag import RAG

                self._rag = RAG()
            except Exception:
                return None
        return self._rag

    async def retrieve(
        self,
        graph: GraphService,
        query: str,
        project_id: str,
        options: RetrievalOptions,
    ) -> list[dict]:
        results: list[dict] = []
        seen_keys: set = set()

        def _add_items(items: list[dict], source: str):
            score = _SOURCE_SCORE.get(source, 0.3)
            for it in items:
                props = it.get("item") or {}
                # Deduplication key based on path or name or element id
                key = (
                    props.get("path")
                    or props.get("name")
                    or props.get("title")
                    or str(props)
                )
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    results.append({**it, "source": source, "score": score})

        # 1. Exact / substring symbol search
        if options.exact_symbol:
            try:
                exact = graph.query(
                    """
                    MATCH (n) WHERE toLower(n.name) CONTAINS toLower($query)
                    RETURN properties(n) as n, labels(n) as type LIMIT $limit
                    """,
                    {"query": query, "limit": options.limit},
                )
                if exact:
                    _add_items(
                        [{"item": r["n"], "type": r["type"]} for r in exact],
                        "graph_exact",
                    )
            except Exception:
                pass

        # 2. Graph concept traversal
        if options.graph_traversal:
            try:
                traversal = graph.query(
                    """
                    MATCH (c:Concept) WHERE toLower(c.description) CONTAINS toLower($query) OR toLower(c.name) CONTAINS toLower($query)
                    MATCH (c)-[:IMPLEMENTS|RELATED_TO*1..2]-(related)
                    RETURN DISTINCT properties(related) as related, labels(related) as type LIMIT $limit
                    """,
                    {"query": query, "limit": options.limit},
                )
                if traversal:
                    _add_items(
                        [{"item": r["related"], "type": r["type"]} for r in traversal],
                        "graph_traversal",
                    )
            except Exception:
                pass

        # 3. Full-text / property-wide search
        if options.full_text and len(results) < options.limit:
            try:
                ft = graph.query(
                    """
                    MATCH (n)
                    WHERE toLower(n.name) CONTAINS toLower($query)
                       OR (n.signature IS NOT NULL AND toLower(n.signature) CONTAINS toLower($query))
                       OR (n.docstring IS NOT NULL AND toLower(n.docstring) CONTAINS toLower($query))
                       OR (n.description IS NOT NULL AND toLower(n.description) CONTAINS toLower($query))
                       OR (n.title IS NOT NULL AND toLower(n.title) CONTAINS toLower($query))
                    RETURN properties(n) as n, labels(n) as type LIMIT $limit
                    """,
                    {"query": query, "limit": options.limit},
                )
                if ft:
                    _add_items(
                        [{"item": r["n"], "type": r["type"]} for r in ft],
                        "graph_fulltext",
                    )
            except Exception:
                pass

        # 4. DeepWiki RAG fallback
        if options.deepwiki_rag and len(results) < options.limit:
            rag = self._get_rag()
            if rag is not None:
                try:
                    rag_results = await rag.acall(query)
                    if rag_results and rag_results[0].documents:
                        _add_items(
                            [
                                {"item": doc, "type": "rag_chunk"}
                                for doc in rag_results[0].documents[: options.limit]
                            ],
                            "deepwiki_rag",
                        )
                except Exception:
                    pass

        # Sort combined results by score descending
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[: options.limit]
