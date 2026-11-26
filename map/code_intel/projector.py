import os

from map.graph import GraphService, GraphBatch, Provenance, SourceType, ExtractionMethod
from .parser import ParseResult
from .resolver import ResolvedImport, ResolvedCall


class StaticGraphProjector:
    def __init__(self, graph: GraphService):
        self.graph = graph

    def project(
        self,
        parse_results: list[ParseResult],
        resolved_imports: list[ResolvedImport],
        resolved_calls: list[ResolvedCall],
        head_sha: str,
        project: dict | None = None,
        repo_root: str = "",
    ) -> GraphBatch:
        batch = GraphBatch()
        prov = Provenance(
            source=SourceType.STATIC_ANALYSIS,
            extraction_method=ExtractionMethod.TREE_SITTER,
            confidence=1.0,
            source_revision=head_sha,
        )

        project_pending = None
        if project:
            project_pending = batch.add_node(
                "Project",
                {
                    "name": project.get("name", ""),
                    "repo_url": project.get("repo_url", ""),
                    "project_key": project.get("project_key", ""),
                    "branch": project.get("branch", "main"),
                    "head_sha": head_sha,
                },
                prov,
                logical_key="project",
            )

        module_pending: dict[str, str] = {}
        module_counts: dict[str, int] = {}
        file_nodes: dict[str, str] = {}

        for pr in parse_results:
            rel_path = self._rel(pr.file_path, repo_root)
            module_name = rel_path.split("/")[0] if "/" in rel_path else "(root)"

            if module_name not in module_pending:
                module_pending[module_name] = batch.add_node(
                    "Module",
                    {"name": module_name, "path": module_name, "language": pr.language},
                    prov,
                    logical_key=f"module:{module_name}",
                )
                if project_pending:
                    batch.add_edge(project_pending, "CONTAINS", module_pending[module_name], {}, prov)
            module_counts[module_name] = module_counts.get(module_name, 0) + 1

            file_id = batch.add_node(
                "File",
                {
                    "path": rel_path,
                    "hash": self._hash_file(pr.file_path),
                    "language": pr.language,
                    "lines": self._count_lines(pr.file_path),
                    "module": module_name,
                },
                prov,
                logical_key=f"file:{pr.file_path}",
            )
            file_nodes[pr.file_path] = file_id
            batch.add_edge(module_pending[module_name], "CONTAINS", file_id, {}, prov)

            for fn in pr.functions:
                fn_id = batch.add_node(
                    "Function",
                    {
                        "name": fn.name,
                        "signature": fn.signature,
                        "start_line": fn.start_line,
                        "end_line": fn.end_line,
                        "docstring": fn.docstring,
                        "file_path": rel_path,
                    },
                    prov,
                    logical_key=f"fn:{pr.file_path}:{fn.name}:{fn.start_line}",
                )
                batch.add_edge(file_id, "DEFINES", fn_id, {}, prov)

            for cl in pr.classes:
                cl_id = batch.add_node(
                    "Class",
                    {
                        "name": cl.name,
                        "file_path": rel_path,
                        "start_line": cl.start_line,
                        "end_line": cl.end_line,
                        "docstring": cl.docstring,
                        "methods": cl.methods,
                    },
                    prov,
                    logical_key=f"cl:{pr.file_path}:{cl.name}",
                )
                batch.add_edge(file_id, "DEFINES", cl_id, {}, prov)

        for imp in resolved_imports:
            from_id = file_nodes.get(imp.from_file)
            to_id = file_nodes.get(imp.to_file)
            if from_id and to_id:
                batch.add_edge(
                    from_id, "IMPORTS", to_id, {"symbols": imp.symbols}, prov
                )

        fn_nodes: dict[tuple[str, str], str] = {}
        for pr in parse_results:
            for fn in pr.functions:
                fn_nodes[(pr.file_path, fn.name)] = f"fn:{pr.file_path}:{fn.name}:{fn.start_line}"

        for call in resolved_calls:
            caller_key = fn_nodes.get((call.caller_file, call.caller_function))
            callee_key = fn_nodes.get((call.callee_file, call.callee_function))
            if caller_key and callee_key:
                batch.add_edge(
                    caller_key,
                    "CALLS",
                    callee_key,
                    {"line": call.line, "resolved": True},
                    prov,
                )

        return batch

    @staticmethod
    def _rel(file_path: str, repo_root: str) -> str:
        if repo_root:
            try:
                return os.path.relpath(file_path, repo_root).replace("\\", "/")
            except ValueError:
                return file_path.replace("\\", "/")
        return file_path.replace("\\", "/")

    def _hash_file(self, file_path: str) -> str:
        import hashlib

        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except Exception:
            return ""

    def _count_lines(self, file_path: str) -> int:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
