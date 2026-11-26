import os
import relate
from pathlib import Path
from typing import Any
from .schema import DDL_STATEMENTS, UNIQUE_KEYS
from .provenance import Provenance
from .provenance import SourceType, ExtractionMethod
from dataclasses import dataclass, field


@dataclass
class GraphBatch:
    nodes: list[tuple[str, dict, Provenance]] = field(
        default_factory=list
    )
    edges: list[tuple[str, str, str, dict, Provenance]] = field(
        default_factory=list
    )
    node_ids: dict[str, str] = field(default_factory=dict)

    def add_node(
        self, label: str, props: dict, provenance: Provenance, logical_key: str = None
    ) -> str:
        self.nodes.append((label, props, provenance))
        idx = len(self.nodes) - 1
        if logical_key:
            self.node_ids[logical_key] = f"__pending_{idx}__"
        return f"__pending_{idx}__"

    def add_edge(
        self,
        from_id: str,
        rel: str,
        to_id: str,
        props: dict,
        provenance: Provenance,
    ):
        self.edges.append((from_id, rel, to_id, props, provenance))

    def merge(self, other: "GraphBatch"):
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)
        self.node_ids.update(other.node_ids)


class GraphService:
    def __init__(self, graph_path: str | None = None, read_only: bool = False):
        self.path = (
            graph_path
            or os.environ.get("MINDMAP_GRAPH_PATH")
            or str(Path.home() / ".adalflow" / "graphs" / "project.rl")
        )
        self.read_only = read_only
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.store = relate.connect(self.path, read_only=read_only)
        if not read_only:
            self._init_schema()

    def _init_schema(self):
        for stmt in DDL_STATEMENTS:
            self.store.execute(stmt)

    def close(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass

    def __enter__(self) -> "GraphService":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @staticmethod
    def exists(graph_path: str) -> bool:
        return bool(graph_path) and os.path.exists(graph_path)

    def upsert_node(
        self, label: str, props: dict, provenance: Provenance
    ) -> str:
        all_props = {**props, **provenance.to_dict()}
        unique_key = UNIQUE_KEYS.get(label, "id")
        keys = (unique_key,) if isinstance(unique_key, str) else tuple(unique_key)

        missing = [k for k in keys if k not in props]
        if missing:
            raise ValueError(
                f"Missing unique key(s) {missing} for label '{label}'"
            )

        if len(keys) == 1:
            merge_clause = f"{keys[0]}: $value"
            params = {"value": props[keys[0]], "props": all_props}
        else:
            merge_clause = ", ".join(f"{k}: ${k}" for k in keys)
            params = {k: props[k] for k in keys}
            params["props"] = all_props

        cypher = f"""
            MERGE (n:{label} {{ {merge_clause} }})
            SET n += $props
            RETURN elementId(n) as id
        """
        cursor = self.store.execute(cypher, params)
        rows = list(cursor)
        return rows[0]["id"] if rows else None

    def upsert_edge(
        self,
        from_id: str,
        rel_type: str,
        to_id: str,
        props: dict,
        provenance: Provenance,
    ):
        all_props = {**props, **provenance.to_dict()}
        cypher = f"""
            MATCH (a), (b)
            WHERE elementId(a) = $from_id AND elementId(b) = $to_id
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $props
        """
        self.store.execute(cypher, {"from_id": from_id, "to_id": to_id, "props": all_props})

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        cursor = self.store.execute(cypher, params or {})
        return [dict(row) for row in cursor]

    def query_single(self, cypher: str, params: dict | None = None) -> dict | None:
        results = self.query(cypher, params)
        return results[0] if results else None

    def commit_batch(self, batch: GraphBatch) -> dict[str, str]:
        pending_to_eid: dict[str, str] = {}
        for idx, (label, props, prov) in enumerate(batch.nodes):
            eid = self.upsert_node(label, props, prov)
            if eid is not None:
                pending_to_eid[f"__pending_{idx}__"] = eid

        for from_id, rel, to_id, props, prov in batch.edges:
            from_eid = pending_to_eid.get(from_id, from_id)
            to_eid = pending_to_eid.get(to_id, to_id)
            if (
                from_eid
                and to_eid
                and not str(from_eid).startswith("__pending")
                and not str(to_eid).startswith("__pending")
            ):
                self.upsert_edge(from_eid, rel, to_eid, props, prov)

        return pending_to_eid

    def get_node_by_id(self, element_id: str) -> dict | None:
        cypher = "MATCH (n) WHERE elementId(n) = $id RETURN n, labels(n) as labels"
        return self.query_single(cypher, {"id": element_id})

    def get_project(self, repo_url: str) -> dict | None:
        cypher = "MATCH (p:Project {repo_url: $url}) RETURN p"
        return self.query_single(cypher, {"url": repo_url})