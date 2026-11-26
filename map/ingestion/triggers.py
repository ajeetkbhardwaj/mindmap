import os
import subprocess

from map import storage
from map.graph import GraphService
from map.ingestion.deepwiki_adapter import DeepWikiAdapter


def _graph_path(repo_path: str) -> str:
    override = os.environ.get("MINDMAP_GRAPH_PATH")
    if override:
        return override
    return storage.graph_path_for(repo_path)


def _repo_path(request) -> str:
    from mind.api.repository import Repo

    repo = Repo(request.repo_url, request.type, access_token=request.token)
    return storage.normalize_path(repo.save_path)


async def trigger_wiki_projection(request, structure, pages: dict):
    from mind.api.schemas import RepoInfo, WikiCacheData

    repo_path = _repo_path(request)
    head_sha = get_head_sha(repo_path) if os.path.isdir(repo_path) else "unknown"

    cache = WikiCacheData(
        wiki_structure=structure,
        generated_pages=pages,
        repo=RepoInfo(
            owner=request.owner,
            repo=request.repo,
            type=request.type,
            token=None,
            repoUrl=request.repo_url,
        ),
        provider=request.provider,
        model=request.model,
    )

    storage.register_project(request.repo_url, repo_path)
    path = _graph_path(repo_path)

    # Short-lived connection: commit on the calling thread (Relate is
    # thread-affine) and close immediately so other processes can open the file.
    try:
        with GraphService(path) as graph:
            adapter = DeepWikiAdapter(graph)
            batch = adapter.extract_from_wiki_cache(cache, request.repo_url, head_sha)
            graph.commit_batch(batch)

        written = storage.export_wiki_markdown(repo_path, pages)
        manifest = storage.read_manifest(repo_path)
        manifest["last_wiki_sha"] = head_sha
        manifest["wiki_pages"] = len(written)
        storage.write_manifest(repo_path, manifest)
        return {"ok": True, "pages": len(written)}
    except Exception as exc:
        import logging
        logging.getLogger("mindmap.triggers").exception("Wiki projection failed")
        raise


async def trigger_codemap_projection(request, codemap):
    repo_path = _repo_path(request)
    head_sha = get_head_sha(repo_path) if os.path.isdir(repo_path) else "unknown"

    storage.register_project(request.repo_url, repo_path)
    path = _graph_path(repo_path)

    try:
        with GraphService(path) as graph:
            adapter = DeepWikiAdapter(graph)
            batch = adapter.extract_from_codemap(codemap, request.repo_url, head_sha)
            graph.commit_batch(batch)

        written = storage.export_codemap_markdown(repo_path, codemap)
        manifest = storage.read_manifest(repo_path)
        manifest["last_codemap_sha"] = head_sha
        storage.write_manifest(repo_path, manifest)
        return {"ok": True, "sections": len(written)}
    except Exception as exc:
        import logging
        logging.getLogger("mindmap.triggers").exception("Codemap projection failed")
        raise


def get_head_sha(repo_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"
