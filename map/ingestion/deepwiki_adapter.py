import hashlib

from map.graph import GraphBatch, GraphService, Provenance, SourceType, ExtractionMethod


class DeepWikiAdapter:
    def __init__(self, graph: GraphService):
        self.graph = graph

    def extract_from_wiki_cache(
        self, cache, repo_url: str, head_sha: str
    ) -> GraphBatch:
        batch = GraphBatch()
        prov = Provenance(
            source=SourceType.DEEPWIKI_WIKI,
            extraction_method=ExtractionMethod.LLM_STRUCTURE,
            confidence=0.85,
            source_revision=head_sha,
        )

        from map.storage import canonical_project_id

        project_id = batch.add_node(
            "Project",
            {
                "name": f"{cache.repo.owner}/{cache.repo.repo}"
                if cache.repo
                else repo_url,
                "repo_url": repo_url,
                "project_key": canonical_project_id(repo_url),
                "branch": "main",
                "head_sha": head_sha,
                "provider": cache.provider or "",
                "model": cache.model or "",
            },
            prov,
            logical_key="project",
        )

        for section in cache.wiki_structure.sections or []:
            mod_id = batch.add_node(
                "Module",
                {
                    "name": section.title,
                    "path": self._infer_module_path(section, cache) or section.title,
                    "language": "unknown",
                },
                prov,
                logical_key=f"module:{section.id}",
            )
            batch.add_edge(project_id, "CONTAINS", mod_id, {}, prov)

        page_prov = Provenance(
            source=SourceType.DEEPWIKI_WIKI,
            extraction_method=ExtractionMethod.LLM_PAGE,
            confidence=0.8,
            source_revision=head_sha,
        )
        for page_id, page in (cache.generated_pages or {}).items():
            page_title = page.title if hasattr(page, "title") else str(page_id)
            page_content = (page.content if hasattr(page, "content") else "") or ""
            safe_pid = self._safe_name(page_id)
            safe_title = self._safe_name(page_title)
            page_node = batch.add_node(
                "WikiPage",
                {
                    "title": page_title,
                    "content": page_content[:50_000],  # cap at 50 KB for graph storage
                    "content_hash": hashlib.sha256(
                        page_content.encode("utf-8")
                    ).hexdigest()[:16],
                    "file_path": f"deepwiki/wiki/{safe_pid}-{safe_title}.md",
                    "source": "deepwiki_generation",
                    "language": "unknown",
                    "section_id": page_id,
                },
                page_prov,
                logical_key=f"page:{page_id}",
            )

            for file_path in page.filePaths or []:
                file_id = self._resolve_file_id(file_path)
                if file_id:
                    batch.add_edge(
                        page_node,
                        "DOCUMENTS",
                        file_id,
                        {"excerpt": self._extract_excerpt(page.content, file_path)},
                        page_prov,
                    )

        return batch

    def extract_from_codemap(self, codemap, repo_url: str, head_sha: str) -> GraphBatch:
        batch = GraphBatch()
        prov = Provenance(
            source=SourceType.DEEPWIKI_CODEMAP,
            extraction_method=ExtractionMethod.LLM_CODEMAP,
            confidence=0.9,
            source_revision=head_sha,
        )

        for section in codemap.sections or []:
            concept_id = batch.add_node(
                "Concept",
                {
                    "name": section.title,
                    "description": section.guide or f"Codemap section: {section.title}",
                    "source": "codemap",
                },
                prov,
                logical_key=f"concept:{section.id}",
            )

            for step in section.steps or []:
                if step.citation and step.citation.file_path:
                    file_id = self._resolve_file_id(step.citation.file_path)
                    if file_id:
                        batch.add_edge(
                            file_id,
                            "IMPLEMENTS",
                            concept_id,
                            {
                                "completeness": "partial",
                                "step": step.label,
                            },
                            prov,
                        )

        return batch

    @staticmethod
    def _safe_name(value: str) -> str:
        import re
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")
        return name or "untitled"

    def _resolve_file_id(self, rel_path: str) -> str | None:
        if not self.graph:
            return None
        normalised = rel_path.replace("\\", "/")
        row = self.graph.query_single(
            "MATCH (f:File) WHERE replace(f.path, '\\\\', '/') = $p RETURN elementId(f) as id",
            {"p": normalised},
        )
        return row.get("id") if row else None

    def _infer_module_path(self, section, cache) -> str:
        pages = cache.wiki_structure.pages or []
        for page in pages:
            if page.id in (section.pages or []) and page.filePaths:
                return "/".join(page.filePaths[0].split("/")[:-1])
        return ""

    def _extract_excerpt(self, content: str, file_path: str) -> str:
        return (content or "")[:200]
