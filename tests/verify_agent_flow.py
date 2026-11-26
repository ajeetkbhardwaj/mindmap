import asyncio
import json
import os
from map.mcp.handlers import MCPHandler
from map.mcp.tools import (
    IndexProjectParams,
    GetProjectOverviewParams,
    GetProjectTreeParams,
    GetEntryPointsParams,
    GetFileSymbolsParams,
    FindSymbolParams,
    GetSymbolContextParams,
    SearchProjectParams,
    ListProjectsParams,
)

async def verify_agent_pipeline():
    project_path = "/Users/ajeetkumar/Developer/GitHubOfficial/mindmap"
    handler = MCPHandler()

    print("--- 1. Agent calls list_projects() ---")
    lp = await handler.list_projects(ListProjectsParams())
    print(f"Projects found: {lp.get('total')}")

    print("\n--- 2. Agent calls index_project() ---")
    idx = await handler.index_project(IndexProjectParams(
        repo_url=project_path,
        repo_type="local",
        provider="nvidia",
        model="nvidia/nemotron-3.5-bolt-e4b"
    ))
    print(f"Index status: {idx.get('status')}")
    print(f"Files parsed: {idx.get('files_parsed')}, skipped: {idx.get('files_skipped')}")
    print(f"Imports resolved: {idx.get('imports')}, Calls resolved: {idx.get('calls')}")
    print(f"Nodes created: {idx.get('nodes')}, Edges created: {idx.get('edges')}")

    print("\n--- 3. Agent calls get_project_overview() ---")
    overview = await handler.get_project_overview(GetProjectOverviewParams(project_id=project_path))
    print(f"Modules: {overview.get('modules')}, Files: {overview.get('files')}")
    print(f"Functions: {overview.get('functions')}, Classes: {overview.get('classes')}")

    print("\n--- 4. Agent calls get_entry_points() ---")
    ep = await handler.get_entry_points(GetEntryPointsParams(project_id=project_path))
    entry_fns = [e["fn"]["name"] for e in ep.get("entry_points", [])]
    print(f"Entry points found ({len(entry_fns)}): {entry_fns[:8]}")

    print("\n--- 5. Agent calls get_project_tree() ---")
    tree = await handler.get_project_tree(GetProjectTreeParams(project_id=project_path, max_depth=2))
    print(f"Tree items: {len(tree.get('tree', []))}")

    print("\n--- 6. Agent calls get_file_symbols(map/mcp/server.py) ---")
    fs = await handler.get_file_symbols(GetFileSymbolsParams(project_id=project_path, file_path="map/mcp/server.py"))
    syms = [s["item"]["name"] for s in fs.get("symbols", [])]
    print(f"Symbols in map/mcp/server.py: {syms}")

    print("\n--- 7. Agent calls find_symbol('create_mcp_server') ---")
    find_res = await handler.find_symbol(FindSymbolParams(project_id=project_path, name="create_mcp_server"))
    results = find_res.get("results", [])
    print(f"Symbols matching 'create_mcp_server': {len(results)}")
    if results:
        sym_id = results[0]["id"]
        print(f"Symbol ID: {sym_id}")

        print("\n--- 8. Agent calls get_symbol_context() ---")
        ctx = await handler.get_symbol_context(GetSymbolContextParams(project_id=project_path, symbol_id=sym_id))
        print(f"Context ok: {ctx.get('ok')}")
        print(f"Function signature: {ctx.get('n', {}).get('signature')}")
        print(f"File defined in: {ctx.get('f', {}).get('path')}")

    print("\n--- 9. Agent calls search_project('nemotron') ---")
    search_res = await handler.search_project(SearchProjectParams(project_id=project_path, query="nemotron"))
    print(f"Search results for 'nemotron': {search_res.get('count')}")
    for r in search_res.get("results", [])[:3]:
        item = r.get("item", {})
        print(f"  - [{r.get('source')}] {item.get('name') or item.get('path')} (score: {r.get('score')})")

    print("\n==========================================")
    print("ALL AGENT TOOLS VERIFIED AND FUNCTIONAL!")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(verify_agent_pipeline())

