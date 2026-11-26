import hashlib
import os
from map.graph import GraphService


class StalenessDetector:
    def __init__(self, graph: GraphService, repo_root: str = ""):
        self.graph = graph
        self.repo_root = repo_root

    def detect(self, project_id: str) -> list[dict]:
        stale = []

        # 1. Detect calls where line numbers have shifted outside function boundaries
        shifted = self.graph.query("""
            MATCH (caller:Function)-[r:CALLS]->(callee:Function)
            WHERE caller.file_path = callee.file_path
            AND r.line IS NOT NULL
            AND (caller.end_line < r.line OR callee.start_line > r.line)
            RETURN properties(r) as r, properties(caller) as caller, properties(callee) as callee
        """)
        for row in shifted:
            stale.append({
                "type": "CALLS_LINE_SHIFT",
                "relationship": row.get("r"),
                "caller": row.get("caller"),
                "callee": row.get("callee"),
            })

        # 2. Compare stored content_hash of WikiPage against current file on disk
        pages = self.graph.query("""
            MATCH (doc:WikiPage)
            WHERE doc.content_hash IS NOT NULL AND doc.file_path IS NOT NULL
            RETURN properties(doc) as doc
        """)
        for row in pages:
            doc = row.get("doc", {})
            fp = doc.get("file_path")
            if not fp:
                continue
            full_path = os.path.join(self.repo_root, fp) if self.repo_root else fp
            if not os.path.exists(full_path):
                stale.append({
                    "type": "DOCS_FILE_MISSING",
                    "wiki_page": doc,
                    "file_path": fp,
                })
                continue
            try:
                with open(full_path, "rb") as fh:
                    current_hash = hashlib.sha256(fh.read()).hexdigest()[:16]
                if current_hash != doc.get("content_hash"):
                    stale.append({
                        "type": "DOCS_CONTENT_CHANGED",
                        "wiki_page": doc,
                        "stored_hash": doc.get("content_hash"),
                        "current_hash": current_hash,
                        "file_path": fp,
                    })
            except Exception:
                pass

        return stale