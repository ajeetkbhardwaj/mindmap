import subprocess
from map.graph import GraphService
from map.code_intel import CodeParser, SymbolResolver, StaticGraphProjector
from map.graph import Provenance, SourceType, ExtractionMethod


class IncrementalSync:
    def __init__(self, graph: GraphService):
        self.graph = graph
        self.parser = CodeParser()
        self.resolver = SymbolResolver("")
        self.projector = StaticGraphProjector(graph)

    async def sync(self, project_id: str, repo_path: str) -> dict:
        current_sha = self._get_head_sha(repo_path)
        last_sha = self._get_last_indexed_sha(project_id)

        if current_sha == last_sha:
            return {"changed": False, "sha": current_sha}

        changed_files = self._get_changed_files(repo_path, last_sha, current_sha)

        parse_results = []
        for f in changed_files:
            full = f"{repo_path}/{f}"
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fp:
                    content = fp.read()
                parse_results.append(self.parser.parse_file(full, content))
            except Exception as e:
                print(f"Failed to parse {f}: {e}")

        import os
        from map.storage import canonical_project_id

        self.resolver.project_root = repo_path
        # Prime resolver with known symbols from the existing graph
        existing_symbols = self.graph.query("""
            MATCH (fn:Function) RETURN fn.file_path as file_path, fn.name as name
        """)
        for row in existing_symbols:
            fp = row.get("file_path")
            name = row.get("name")
            if fp and name:
                full_fp = os.path.join(repo_path, fp)
                mod = self.resolver._file_to_module(full_fp)
                self.resolver.symbol_index[(mod, name)] = full_fp

        self.resolver.build_index(parse_results)

        imports = self.resolver.resolve_imports(parse_results)
        calls = self.resolver.resolve_calls(parse_results)

        batch = self.projector.project(
            parse_results, imports, calls, current_sha, repo_root=repo_path
        )
        self.graph.commit_batch(batch)

        proj_key = canonical_project_id(project_id)
        self.graph.query(
            "MATCH (p:Project) WHERE p.repo_url = $pid OR p.name = $pid OR p.project_key = $key SET p.head_sha = $sha, p.project_key = $key",
            {"pid": project_id, "sha": current_sha, "key": proj_key}
        )

        return {"changed": True, "files": changed_files, "sha": current_sha}

    def _get_changed_files(self, repo_path: str, from_sha: str, to_sha: str) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "diff", "--name-only", from_sha, to_sha],
                capture_output=True, text=True, check=True
            )
            return [f for f in result.stdout.strip().split("\n") if f]
        except Exception:
            return []

    def _get_head_sha(self, repo_path: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_last_indexed_sha(self, project_id: str) -> str:
        from map.storage import canonical_project_id

        result = self.graph.query_single(
            "MATCH (p:Project) WHERE p.project_key = $key OR p.repo_url = $pid OR p.name = $pid RETURN p.head_sha as sha",
            {"pid": project_id, "key": canonical_project_id(project_id)},
        )
        return result.get("sha", "") if result else ""
