import pytest
from map.ingestion.deepwiki_adapter import DeepWikiAdapter
from mind.api.schemas import WikiCacheData, WikiStructureModel, WikiPage, RepoInfo

def test_deepwiki_adapter_projection():
    adapter = DeepWikiAdapter(None)
    structure = WikiStructureModel(id="root", title="Structure", description="", pages=[], sections=[])
    pages = {
        "page_1": WikiPage(id="page_1", title="Authentication Overview", content="# Auth\nThis explains JWT auth.", filePaths=["auth.py"], importance="high", relatedPages=[])
    }
    repo_info = RepoInfo(owner="test", repo="app", type="local", repoUrl="test/app")
    cache = WikiCacheData(wiki_structure=structure, generated_pages=pages, repo=repo_info)

    batch = adapter.extract_from_wiki_cache(cache, "test/app", "head_sha_123")
    assert len(batch.nodes) >= 2
    labels = [n[0] for n in batch.nodes]
    assert "Project" in labels
    assert "WikiPage" in labels

    # Check WikiPage props
    wp_node = [n for n in batch.nodes if n[0] == "WikiPage"][0]
    props = wp_node[1]
    assert props["title"] == "Authentication Overview"
    assert "JWT auth" in props["content"]
    assert props["content_hash"] is not None
