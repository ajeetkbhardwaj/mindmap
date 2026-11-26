import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Resource,
    TextResourceContents,
    CallToolResult,
)

from .app_ui import get_mindmap_app_html
from .tools import (
    MCP_TOOLS,
    MINDMAP_APP_URI,
    IndexProjectParams,
    SearchProjectParams,
    FindSymbolParams,
    GetSymbolContextParams,
    GetDependenciesParams,
    TraceCallPathParams,
    GetImpactAnalysisParams,
    FindRelatedDocsParams,
    GetTestsForSymbolParams,
    GetGitContextParams,
    QueryProjectGraphParams,
    GetGraphSchemaParams,
    GetProjectOverviewParams,
    GenerateWikiParams,
    GenerateCodemapParams,
    ListProjectsParams,
    GetFileSymbolsParams,
    ReadWikiPageParams,
    GetEntryPointsParams,
    GetProjectTreeParams,
    GetJobStatusParams,
    ViewMindmapParams,
)

TOOL_PARAMS = {
    "index_project": IndexProjectParams,
    "update_project": IndexProjectParams,
    "get_project_overview": GetProjectOverviewParams,
    "search_project": SearchProjectParams,
    "find_symbol": FindSymbolParams,
    "get_symbol_context": GetSymbolContextParams,
    "get_dependencies": GetDependenciesParams,
    "trace_call_path": TraceCallPathParams,
    "get_impact_analysis": GetImpactAnalysisParams,
    "find_related_docs": FindRelatedDocsParams,
    "get_tests_for_symbol": GetTestsForSymbolParams,
    "get_git_context": GetGitContextParams,
    "query_project_graph": QueryProjectGraphParams,
    "get_graph_schema": GetGraphSchemaParams,
    "generate_wiki": GenerateWikiParams,
    "generate_codemap": GenerateCodemapParams,
    "list_projects": ListProjectsParams,
    "get_file_symbols": GetFileSymbolsParams,
    "read_wiki_page": ReadWikiPageParams,
    "get_entry_points": GetEntryPointsParams,
    "get_project_tree": GetProjectTreeParams,
    "get_job_status": GetJobStatusParams,
    "view_mindmap": ViewMindmapParams,
}


def create_mcp_server() -> Server:
    from .handlers import MCPHandler

    server = Server("deepwiki-relate-bridge")
    handler = MCPHandler()

    @server.list_tools()
    async def list_tools():
        return MCP_TOOLS

    @server.list_resources()
    async def list_resources():
        return [
            Resource(
                uri=MINDMAP_APP_URI,
                name="Mindmap Interactive Graph App",
                description="Visual knowledge graph viewer for project architecture and symbols",
                mimeType="text/html;profile=mcp-app",
                meta={
                    "ui": {
                        "prefersBorder": False,
                        "csp": {
                            "resourceDomains": [],
                            "connectDomains": [],
                        },
                    }
                },
            )
        ]

    @server.read_resource()
    async def read_resource(uri: str):
        if str(uri) == MINDMAP_APP_URI:
            return [
                TextResourceContents(
                    uri=uri,
                    mimeType="text/html;profile=mcp-app",
                    text=get_mindmap_app_html(),
                )
            ]
        raise ValueError(f"Resource not found: {uri}")

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        model = TOOL_PARAMS.get(name)
        if model is None:
            raise ValueError(f"Unknown tool: {name}")
        params = model(**(arguments or {}))
        method = getattr(handler, name)
        result = await method(params)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, default=str))],
            structuredContent=result,
        )

    return server


async def main_stdio():
    server = create_mcp_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main_sse(host: str = "0.0.0.0", port: int = 8002):
    import contextlib

    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    server = create_mcp_server()
    session_manager = StreamableHTTPSessionManager(app=server, stateless=False)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield

    app = Starlette(
        routes=[
            Mount("/mcp", app=session_manager.handle_request),
            Mount("/", app=session_manager.handle_request),
        ],
        lifespan=lifespan,
    )
    uvicorn.run(app, host=host, port=port)
