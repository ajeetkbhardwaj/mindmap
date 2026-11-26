import pytest
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from map.mcp.handlers import MCPHandler
from map.mcp.tools import (
    IndexProjectParams,
    GetProjectOverviewParams,
    SearchProjectParams,
    FindSymbolParams,
    GetSymbolContextParams,
    GetDependenciesParams,
    GetFileSymbolsParams,
    GetEntryPointsParams,
    GetProjectTreeParams,
    ListProjectsParams,
    GetGraphSchemaParams,
    QueryProjectGraphParams,
    ReadWikiPageParams,
)
from map.graph import GraphService
import map.storage as storage


@pytest.fixture
def temp_project():
    temp_dir = tempfile.mkdtemp(prefix="mindmap_test_")
    # Create simple python project files
    main_py = Path(temp_dir) / "main.py"
    main_py.write_text(
        "import helper\n\ndef main():\n    return helper.greet('world')\n",
        encoding="utf-8",
    )
    helper_py = Path(temp_dir) / "helper.py"
    helper_py.write_text(
        "def greet(name: str):\n    return f'Hello, {name}'\n",
        encoding="utf-8",
    )
    # Init git repo
    os.system(f"git -C {temp_dir} init && git -C {temp_dir} config user.email 'test@test.com' && git -C {temp_dir} config user.name 'Test' && git -C {temp_dir} add . && git -C {temp_dir} commit -m 'initial commit'")
    
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_full_mcp_pipeline(temp_project):
    handler = MCPHandler()

    # 1. Index project
    idx_res = await handler.index_project(IndexProjectParams(repo_url=temp_project, repo_type="local"))
    assert idx_res.get("ok") is True
    assert idx_res.get("status") == "indexed"
    assert idx_res.get("files_parsed") >= 2

    # 2. List projects
    list_res = await handler.list_projects(ListProjectsParams())
    assert list_res.get("ok") is True
    assert any(p["repo_path"] == storage.normalize_path(temp_project) for p in list_res["projects"])

    # 3. Get project overview
    overview = await handler.get_project_overview(GetProjectOverviewParams(project_id=temp_project))
    assert overview.get("ok") is True
    assert overview.get("files", 0) >= 2
    assert overview.get("functions", 0) >= 2

    # 4. Find symbol
    sym_res = await handler.find_symbol(FindSymbolParams(project_id=temp_project, name="greet"))
    assert sym_res.get("ok") is True
    assert len(sym_res.get("results", [])) > 0
    greet_id = sym_res["results"][0]["id"]

    # 5. Get symbol context
    ctx = await handler.get_symbol_context(GetSymbolContextParams(project_id=temp_project, symbol_id=greet_id))
    assert ctx.get("ok") is True

    # 6. Get dependencies
    deps = await handler.get_dependencies(GetDependenciesParams(project_id=temp_project, target_id=greet_id))
    assert deps.get("ok") is True

    # 7. Get file symbols
    fs = await handler.get_file_symbols(GetFileSymbolsParams(project_id=temp_project, file_path="helper.py"))
    assert fs.get("ok") is True
    assert any(s["item"]["name"] == "greet" for s in fs["symbols"])

    # 8. Get entry points
    ep = await handler.get_entry_points(GetEntryPointsParams(project_id=temp_project))
    assert ep.get("ok") is True
    assert any(e["fn"]["name"] == "main" for e in ep["entry_points"])

    # 9. Get project tree
    tree = await handler.get_project_tree(GetProjectTreeParams(project_id=temp_project))
    assert tree.get("ok") is True
    assert len(tree.get("tree", [])) > 0

    # 10. Search project
    srch = await handler.search_project(SearchProjectParams(project_id=temp_project, query="greet"))
    assert srch.get("ok") is True
    assert len(srch.get("results", [])) > 0

    # 11. Graph schema
    schema = await handler.get_graph_schema(GetGraphSchemaParams(project_id=temp_project))
    assert schema.get("ok") is True
    assert "node_labels" in schema

    # 12. Safe cypher query
    safe_q = await handler.query_project_graph(QueryProjectGraphParams(
        project_id=temp_project, cypher="MATCH (n) RETURN count(n) as total"
    ))
    assert safe_q.get("ok") is True
    assert safe_q["results"][0]["total"] > 0

    # 13. Unsafe cypher query rejected
    unsafe_q = await handler.query_project_graph(QueryProjectGraphParams(
        project_id=temp_project, cypher="MATCH (n) DETACH DELETE n"
    ))
    assert unsafe_q.get("ok") is False
    assert unsafe_q.get("error_code") == "UNSAFE_QUERY"

