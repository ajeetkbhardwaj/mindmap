import json
import os
import sys
import asyncio
import uuid
from contextlib import contextmanager
from pathlib import Path

from map import storage
from map.graph import GraphService
from map.retrieval.hybrid import HybridRetriever
from map.mcp.tools import *


# In-memory async job store for wiki/codemap generation
_jobs: dict[str, dict] = {}


class MCPHandler:
    """MCP tool handlers backed by per-project ``.mindmap/graph.rl`` files.

    Connections are short-lived (opened per call, closed after) so that the
    MCP server and the DeepWiki projection hooks (separate processes) can take
    turns on the same redb file without holding a long-lived lock.
    """

    def __init__(self, graph_path: str | None = None):
        self._override = graph_path or os.environ.get("MINDMAP_GRAPH_PATH")
        self.retriever = HybridRetriever()

    # ------------------------------------------------------------------
    # Standard response helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _ok(data: dict) -> dict:
        return {"ok": True, **data}

    @staticmethod
    def _error(code: str, message: str, project_id: str = "") -> dict:
        return {"ok": False, "error_code": code, "error": message, "project_id": project_id}

    # ------------------------------------------------------------------
    # Graph resolution / connection management
    # ------------------------------------------------------------------
    def _graph_path_for(self, project_id: str) -> str | None:
        if self._override:
            return self._override
        repo_path = storage.repo_path_for(project_id)
        if repo_path:
            return storage.graph_path_for(repo_path)
        return None

    @contextmanager
    def _read_graph(self, project_id: str):
        path = self._graph_path_for(project_id)
        if not path or not os.path.exists(path):
            yield None
            return
        try:
            graph = GraphService(path, read_only=True)
        except Exception:
            yield None
            return
        try:
            yield graph
        finally:
            graph.close()

    @contextmanager
    def _write_graph(self, project_id: str):
        path = self._graph_path_for(project_id)
        if not path:
            path = self._override or str(
                Path.home() / ".adalflow" / "graphs" / "project.rl"
            )
        graph = GraphService(path)
        try:
            yield graph
        finally:
            graph.close()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    async def index_project(self, params: IndexProjectParams) -> dict:
        from map.code_intel import CodeParser, SymbolResolver, StaticGraphProjector
        from map.code_intel.parser import SUPPORTED_LANGUAGES
        from mind.api.repository import Repo

        repo = Repo(params.repo_url, params.repo_type, access_token=params.token)
        repo.download()
        if not repo.downloaded:
            return {"project_id": params.repo_url, "status": "clone_failed"}

        repo_path = repo.save_path
        norm_repo_path = storage.normalize_path(repo_path)
        head_sha = self._git(repo_path, "rev-parse", "HEAD") or "unknown"
        branch = self._git(repo_path, "rev-parse", "--abbrev-ref", "HEAD") or "main"

        parser = CodeParser()
        parse_results = []
        skipped = 0
        for full_path in self._iter_source_files(repo_path, SUPPORTED_LANGUAGES):
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as fp:
                    content = fp.read()
            except Exception:
                skipped += 1
                continue
            result = parser.parse_file(full_path, content)
            if result.language != "unknown":
                parse_results.append(result)

        resolver = SymbolResolver(repo_path)
        resolver.build_index(parse_results)
        imports = resolver.resolve_imports(parse_results)
        calls = resolver.resolve_calls(parse_results)

        # Register before opening so the graph lands in the project dir.
        storage.register_project(params.repo_url, norm_repo_path)
        storage.ensure_gitignore(norm_repo_path)
        graph_path = self._override or storage.graph_path_for(norm_repo_path)

        with GraphService(graph_path) as graph:
            projector = StaticGraphProjector(graph)
            batch = projector.project(
                parse_results,
                imports,
                calls,
                head_sha,
                project={
                    "repo_url": params.repo_url,
                    "name": repo.name,
                    "branch": branch,
                    "project_key": storage.canonical_project_id(params.repo_url),
                },
                repo_root=repo_path,
            )
            graph.commit_batch(batch)

        storage.write_manifest(
            norm_repo_path,
            {
                "project_id": params.repo_url,
                "name": repo.name,
                "repo_url": params.repo_url,
                "branch": branch,
                "head_sha": head_sha,
                "status": "indexed",
                "graph": graph_path,
                "files_parsed": len(parse_results),
                "files_skipped": skipped,
                "imports": len(imports),
                "calls": len(calls),
                "nodes": len(batch.nodes),
                "edges": len(batch.edges),
            },
        )

        res_data = {
            "project_id": params.repo_url,
            "name": repo.name,
            "status": "indexed",
            "graph_path": graph_path,
            "head_sha": head_sha,
            "files_parsed": len(parse_results),
            "files_skipped": skipped,
            "imports": len(imports),
            "calls": len(calls),
            "nodes": len(batch.nodes),
            "edges": len(batch.edges),
        }

        if getattr(params, "generate_docs", False):
            wiki_params = GenerateWikiParams(
                project_id=params.repo_url,
                repo_type=params.repo_type,
                provider=params.provider,
                model=params.model,
                language=params.language,
            )
            job_id = str(uuid.uuid4())
            _jobs[job_id] = {"status": "running", "project_id": params.repo_url}
            asyncio.create_task(self._run_wiki_job(job_id, wiki_params))
            res_data["docs_job_id"] = job_id
            res_data["docs_status"] = "generation_started"

        return self._ok(res_data)

    @staticmethod
    def _git(repo_path: str, *args: str) -> str:
        import subprocess

        try:
            out = subprocess.run(
                ["git", "-C", repo_path, *args],
                capture_output=True,
                text=True,
                check=True,
            )
            return out.stdout.strip()
        except Exception:
            return ""

    @staticmethod
    def _iter_source_files(repo_path: str, extensions: dict):
        ignored_dirs = {
            ".git", "node_modules", "venv", ".venv", "env", "__pycache__",
            "dist", "build", ".next", "target", "vendor", ".mypy_cache",
            ".pytest_cache", "site-packages", ".mindmap", "deepwiki",
        }
        max_bytes = 1_000_000
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for name in files:
                ext = os.path.splitext(name)[1]
                if ext not in extensions:
                    continue
                full = os.path.join(root, name)
                try:
                    if os.path.getsize(full) > max_bytes:
                        continue
                except OSError:
                    continue
                yield full

    async def update_project(self, params: IndexProjectParams) -> dict:
        from map.incremental import IncrementalSync
        from mind.api.repository import Repo

        # First check if project is already registered locally
        repo_path = storage.repo_path_for(params.repo_url)
        if not repo_path:
            # Not registered — try downloading
            repo = Repo(params.repo_url, params.repo_type, access_token=params.token)
            repo.download()
            if not repo.downloaded:
                return self._error("NOT_FOUND", f"Project '{params.repo_url}' not found and could not be cloned.", params.repo_url)
            repo_path = storage.normalize_path(repo.save_path)

        storage.register_project(params.repo_url, repo_path)
        with self._write_graph(params.repo_url) as graph:
            sync = IncrementalSync(graph)
            result = await sync.sync(params.repo_url, repo_path)
        return self._ok({"project_id": params.repo_url, **result})

    # ------------------------------------------------------------------
    # Read-only tools
    # ------------------------------------------------------------------
    async def get_project_overview(self, params: GetProjectOverviewParams) -> dict:
        cypher = """
            MATCH (p:Project)
            WHERE p.project_key = $key OR p.repo_url = $pid OR p.name = $pid
            OPTIONAL MATCH (p)-[:CONTAINS]->(m:Module)
            OPTIONAL MATCH (m)-[:CONTAINS]->(f:File)
            OPTIONAL MATCH (f)-[:DEFINES]->(fn:Function)
            OPTIONAL MATCH (f)-[:DEFINES]->(cl:Class)
            OPTIONAL MATCH (p)-[:CONTAINS*1..3]->()-[:DOCUMENTS]->(c:Concept)
            RETURN properties(p) as p, count(DISTINCT m) as modules, count(DISTINCT f) as files,
                   count(DISTINCT fn) as functions, count(DISTINCT cl) as classes,
                   count(DISTINCT c) as concepts
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            result = graph.query(
                cypher,
                {
                    "pid": params.project_id,
                    "key": storage.canonical_project_id(params.project_id),
                },
            )
        if not result:
            return self._error("PROJECT_NOT_FOUND", f"No project node found for '{params.project_id}'.", params.project_id)
        return self._ok(result[0])

    async def search_project(self, params: SearchProjectParams) -> dict:
        from map.retrieval.hybrid import RetrievalOptions

        options = RetrievalOptions(limit=params.limit)
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = await self.retriever.retrieve(
                graph, params.query, params.project_id, options
            )
        return self._ok({"results": results, "project_id": params.project_id, "count": len(results)})

    async def find_symbol(self, params: FindSymbolParams) -> dict:
        cypher = """
            MATCH (n) WHERE n.name = $name
            RETURN elementId(n) as id, properties(n) as n, labels(n) as type LIMIT 20
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {"name": params.name})
        return self._ok({"results": [{"id": r["id"], "item": r["n"], "type": r["type"]} for r in results]})

    async def get_symbol_context(self, params: GetSymbolContextParams) -> dict:
        cypher = f"""
            MATCH (n) WHERE elementId(n) = $symbol_id
            OPTIONAL MATCH (n)<-[:DEFINES]-(f:File)
            OPTIONAL MATCH (caller:Function)-[:CALLS*1..{params.depth}]->(n)
            OPTIONAL MATCH (n)-[:CALLS*1..{params.depth}]->(callee:Function)
            OPTIONAL MATCH (doc:WikiPage)-[:DOCUMENTS]->(n)
            OPTIONAL MATCH (test:Test)-[:TESTS]->(n)
            RETURN properties(n) as n, properties(f) as f,
                   collect(DISTINCT properties(caller)) as callers,
                   collect(DISTINCT properties(callee)) as callees,
                   collect(DISTINCT properties(doc)) as docs,
                   collect(DISTINCT properties(test)) as tests
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            result = graph.query(cypher, {"symbol_id": params.symbol_id})
        return self._ok(self._format_symbol_context(result[0] if result else {}))

    async def get_dependencies(self, params: GetDependenciesParams) -> dict:
        max_d = params.max_depth
        if params.direction == "incoming":
            direction_clause = f"<-[:IMPORTS|CALLS|DEPENDS_ON*1..{max_d}]-"
        elif params.direction == "outgoing":
            direction_clause = f"-[:IMPORTS|CALLS|DEPENDS_ON*1..{max_d}]->"
        else:
            direction_clause = f"-[:IMPORTS|CALLS|DEPENDS_ON*1..{max_d}]-"

        cypher = f"""
            MATCH (n) WHERE elementId(n) = $target_id
            MATCH (n){direction_clause}(related)
            RETURN DISTINCT properties(related) as related, labels(related) as type LIMIT 50
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {"target_id": params.target_id})
        return self._ok({"dependencies": [{"item": r["related"], "type": r["type"]} for r in results]})

    async def trace_call_path(self, params: TraceCallPathParams) -> dict:
        cypher = f"""
            MATCH (from:Function {{name: $from_symbol}}), (to:Function {{name: $to_symbol}})
            MATCH path = (from)-[:CALLS*1..{params.max_depth}]->(to)
            RETURN path LIMIT $max_paths
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            paths = graph.query(cypher, {
                "from_symbol": params.from_symbol,
                "to_symbol": params.to_symbol,
                "max_paths": params.max_paths,
            })
        return self._ok({"paths": [self._format_path(p) for p in paths]})

    async def get_impact_analysis(self, params: GetImpactAnalysisParams) -> dict:
        cypher = f"""
            MATCH (target) WHERE elementId(target) = $symbol_id
            OPTIONAL MATCH (caller)-[:CALLS*1..{params.max_depth}]->(target)
            OPTIONAL MATCH (importer)-[:IMPORTS*1..{params.max_depth}]->(target)
            OPTIONAL MATCH (test:Test)-[:TESTS]->(target)
            RETURN collect(DISTINCT properties(caller)) as direct_callers,
                   collect(DISTINCT properties(importer)) as importers,
                   collect(DISTINCT properties(test)) as tests
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            result = graph.query(cypher, {"symbol_id": params.symbol_id})
        return self._ok(self._format_impact(result[0] if result else {}))

    async def find_related_docs(self, params: FindRelatedDocsParams) -> dict:
        cypher = """
            MATCH (doc:WikiPage)
            WHERE toLower(doc.content) CONTAINS toLower($query)
               OR toLower(doc.title) CONTAINS toLower($query)
            RETURN properties(doc) as doc LIMIT $limit
        """
        if params.symbol_id:
            cypher = """
                MATCH (doc:WikiPage)-[:DOCUMENTS]->(target)
                WHERE elementId(target) = $symbol_id
                RETURN properties(doc) as doc LIMIT $limit
            """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {"query": params.query, "symbol_id": params.symbol_id, "limit": params.limit})
        return self._ok({"docs": [r["doc"] for r in results]})

    async def get_tests_for_symbol(self, params: GetTestsForSymbolParams) -> dict:
        cypher = """
            MATCH (test:Test)-[:TESTS]->(target)
            WHERE elementId(target) = $symbol_id
            RETURN properties(test) as test LIMIT $limit
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {"symbol_id": params.symbol_id, "limit": params.limit})
        return self._ok({"tests": [r["test"] for r in results]})

    async def get_git_context(self, params: GetGitContextParams) -> dict:
        cypher = """
            MATCH (c:Commit)-[:CHANGED_IN]->(target)
            WHERE elementId(target) = $target_id
            RETURN properties(c) as c ORDER BY c.timestamp DESC LIMIT $limit
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {"target_id": params.target_id, "limit": params.limit})
        return self._ok({"commits": [r["c"] for r in results]})

    async def query_project_graph(self, params: QueryProjectGraphParams) -> dict:
        if not self._is_safe_query(params.cypher):
            return self._error("UNSAFE_QUERY", "Only read-only Cypher queries are allowed (no CREATE, DELETE, SET, REMOVE, MERGE, DROP, LOAD, CALL, FOREACH, DETACH).", params.project_id)
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(params.cypher, params.params)
        return self._ok({"results": results})

    async def get_graph_schema(self, params: GetGraphSchemaParams) -> dict:
        from map.graph import NODE_LABELS, RELATIONSHIPS
        return self._ok({"node_labels": NODE_LABELS, "relationships": RELATIONSHIPS})

    # ------------------------------------------------------------------
    # Generation (reuses the existing DeepWiki pipeline; hooks write
    # .mindmap/graph.rl nodes + deepwiki/ markdown into the project)
    # ------------------------------------------------------------------
    @staticmethod
    def _owner_repo(project_id: str, owner: str | None, repo: str | None):
        resolved_owner = owner
        resolved_repo = repo
        if not resolved_repo:
            base = project_id.rstrip("/").split("/")[-1].replace(".git", "")
            resolved_repo = base or "repo"
        if not resolved_owner:
            parts = project_id.rstrip("/").split("/")
            if len(parts) >= 2 and "://" in project_id:
                resolved_owner = parts[-2]
            else:
                resolved_owner = "local"
        return resolved_owner, resolved_repo

    async def generate_wiki(self, params: GenerateWikiParams) -> dict:
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {"status": "running", "project_id": params.project_id}
        asyncio.create_task(self._run_wiki_job(job_id, params))
        return self._ok({
            "job_id": job_id,
            "status": "running",
            "project_id": params.project_id,
            "hint": "Call get_job_status(job_id) to poll for completion.",
        })

    async def _run_wiki_job(self, job_id: str, params: GenerateWikiParams):
        from mind.api.schemas import WikiTaskRequest
        from mind.api.services.wiki.tasks import WikiTask, generate_repo_wiki

        owner, repo = self._owner_repo(params.project_id, params.owner, params.repo)
        request = WikiTaskRequest(
            repo_url=params.project_id,
            type=params.repo_type,
            provider=params.provider,
            model=params.model,
            language=params.language,
            owner=owner,
            repo=repo,
        )
        task = WikiTask.from_wiki_request(request)
        try:
            await generate_repo_wiki(task)
        except Exception as exc:
            _jobs[job_id] = {
                "status": "failed",
                "project_id": params.project_id,
                "error": str(exc),
            }
            return

        repo_path = storage.repo_path_for(params.project_id)
        _jobs[job_id] = {
            "status": getattr(task.status, "value", str(task.status)),
            "project_id": params.project_id,
            "error": task.error,
            "pages_done": task.pages_done,
            "pages_total": task.pages_total,
            "deepwiki": os.path.join(repo_path, "deepwiki") if repo_path else None,
        }

    async def generate_codemap(self, params: GenerateCodemapParams) -> dict:
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {"status": "running", "project_id": params.project_id}
        asyncio.create_task(self._run_codemap_job(job_id, params))
        return self._ok({
            "job_id": job_id,
            "status": "running",
            "project_id": params.project_id,
            "hint": "Call get_job_status(job_id) to poll for completion.",
        })

    async def _run_codemap_job(self, job_id: str, params: GenerateCodemapParams):
        from mind.api.schemas import CodeMapRequest
        from mind.api.services.codemap import generate_codemap as _generate

        request = CodeMapRequest(
            repo_url=params.project_id,
            type=params.repo_type,
            question=params.question,
            provider=params.provider,
            model=params.model,
            language=params.language,
        )
        sections = 0
        final = None
        events = 0
        try:
            async for raw in _generate(request):
                events += 1
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                if event.get("type") == "codemap":
                    final = event.get("data")
                    sections = len((final or {}).get("sections", []) or [])
        except Exception as exc:
            _jobs[job_id] = {
                "status": "failed",
                "project_id": params.project_id,
                "error": str(exc),
            }
            return

        repo_path = storage.repo_path_for(params.project_id)
        _jobs[job_id] = {
            "status": "completed",
            "project_id": params.project_id,
            "events": events,
            "sections": sections,
            "title": (final or {}).get("title"),
            "deepwiki": os.path.join(repo_path, "deepwiki") if repo_path else None,
        }

    def _is_safe_query(self, cypher: str) -> bool:
        import re
        tokens = set(re.findall(r'\b[A-Z_]+\b', cypher.upper()))
        _WRITE_KEYWORDS = {"CREATE", "DELETE", "SET", "REMOVE", "MERGE",
                           "DROP", "LOAD", "CALL", "FOREACH", "DETACH"}
        return not (tokens & _WRITE_KEYWORDS)

    def _format_symbol_context(self, data: dict) -> dict:
        if not data:
            return data
        # Clean up None values and empty lists for a compact response
        return {k: v for k, v in data.items() if v is not None and v != []}

    def _format_path(self, path_data: dict) -> dict:
        if not path_data:
            return path_data
        return path_data

    def _format_impact(self, data: dict) -> dict:
        if not data:
            return data
        return {k: v for k, v in data.items() if v is not None and v != []}

    # ------------------------------------------------------------------
    # New tools: list_projects, get_file_symbols, read_wiki_page,
    #            get_entry_points, get_project_tree, get_job_status
    # ------------------------------------------------------------------
    async def list_projects(self, params: ListProjectsParams) -> dict:
        registry = storage.load_registry()
        projects = []
        for pid, repo_path in registry.items():
            manifest = storage.read_manifest(repo_path) if os.path.isdir(repo_path) else {}
            projects.append({
                "project_id": pid,
                "repo_path": repo_path,
                "name": manifest.get("name", pid),
                "status": manifest.get("status", "unknown"),
                "head_sha": manifest.get("head_sha"),
                "files_parsed": manifest.get("files_parsed"),
            })
        return self._ok({"projects": projects, "total": len(projects)})

    async def get_file_symbols(self, params: GetFileSymbolsParams) -> dict:
        cypher = """
            MATCH (f:File {path: $path})-[:DEFINES]->(sym)
            RETURN properties(sym) as sym, labels(sym) as type
            ORDER BY sym.start_line
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {"path": params.file_path.replace("\\", "/")})
        return self._ok({"symbols": [{"item": r["sym"], "type": r["type"]} for r in results]})

    async def read_wiki_page(self, params: ReadWikiPageParams) -> dict:
        cypher = """
            MATCH (w:WikiPage)
            WHERE toLower(w.title) CONTAINS toLower($title)
            RETURN properties(w) as w
            LIMIT 5
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {"title": params.title})
        return self._ok({"pages": [r["w"] for r in results]})

    async def get_entry_points(self, params: GetEntryPointsParams) -> dict:
        cypher = """
            MATCH (f:File)-[:DEFINES]->(fn:Function)
            WHERE fn.name IN ["main", "__main__", "app", "run", "start", "cli",
                              "handler", "lambda_handler", "setup", "create_app"]
               OR fn.name STARTS WITH "on_"
               OR fn.name ENDS WITH "_handler"
               OR fn.name ENDS WITH "_main"
            RETURN properties(fn) as fn, f.path as file_path
            LIMIT 30
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {})
        return self._ok({"entry_points": [{"fn": r["fn"], "file": r["file_path"]} for r in results]})

    async def get_project_tree(self, params: GetProjectTreeParams) -> dict:
        cypher = f"""
            MATCH (p:Project)-[:CONTAINS*1..{params.max_depth}]->(n)
            WHERE NOT n:Function AND NOT n:Class
            RETURN labels(n) as type, n.path as path, n.name as name, n.language as language
            ORDER BY n.path
        """
        with self._read_graph(params.project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{params.project_id}'.", params.project_id)
            results = graph.query(cypher, {})
        return self._ok({"tree": results})

    async def get_job_status(self, params: GetJobStatusParams) -> dict:
        job = _jobs.get(params.job_id)
        if job is None:
            return self._error("JOB_NOT_FOUND", f"No job with id '{params.job_id}'.")
        return self._ok({"job_id": params.job_id, **job})

    async def view_mindmap(self, params: ViewMindmapParams) -> dict:
        project_id = params.project_id
        if not project_id:
            registry = storage.load_registry()
            if registry:
                project_id = list(registry.keys())[-1]
            else:
                project_id = storage.normalize_path(os.getcwd())

        with self._read_graph(project_id) as graph:
            if graph is None:
                return self._error("NO_GRAPH", f"No graph found for project '{project_id}'.", project_id)

            nodes_data = graph.query("""
                MATCH (n)
                WHERE n:Module OR n:File OR n:Function OR n:Class OR n:Concept OR n:WikiPage
                RETURN elementId(n) as id, properties(n) as props, labels(n) as labels
                LIMIT 300
            """)
            nodes = []
            for row in nodes_data:
                lbl = row.get("labels", ["Unknown"])[0] if row.get("labels") else "Unknown"
                p = row.get("props", {})
                nodes.append({
                    "id": row["id"],
                    "type": lbl,
                    "name": p.get("name") or p.get("title") or p.get("path") or "Symbol",
                    "path": p.get("path") or p.get("file_path") or "",
                    "file_path": p.get("file_path") or p.get("path") or "",
                    "signature": p.get("signature") or "",
                    "docstring": p.get("docstring") or p.get("description") or "",
                })

            edges_data = graph.query("""
                MATCH (a)-[r:CONTAINS|DEFINES|CALLS|IMPORTS|DOCUMENTS]->(b)
                RETURN elementId(a) as from_id, type(r) as rel, elementId(b) as to_id
                LIMIT 500
            """)
            edges = [
                {"from": e["from_id"], "rel": e["rel"], "to": e["to_id"]}
                for e in edges_data
            ]

        return self._ok({
            "project_id": project_id,
            "summary": f"Visual graph for {project_id}: {len(nodes)} nodes, {len(edges)} edges.",
            "nodes": nodes,
            "edges": edges,
        })
