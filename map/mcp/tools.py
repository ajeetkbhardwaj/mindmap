from pydantic import BaseModel, Field
from mcp import Tool
from typing import Optional


class IndexProjectParams(BaseModel):
    repo_url: str = Field(description="GitHub/GitLab/Bitbucket URL or local path")
    repo_type: str = Field(default="github", description="github, gitlab, bitbucket, local")
    token: Optional[str] = Field(default=None, description="Access token for private repos")
    provider: str = Field(default="nvidia", description="LLM provider for DeepWiki (e.g. nvidia, openrouter, google, openai, lmstudio, ollama)")
    model: Optional[str] = Field(default=None, description="Specific model to use")
    language: str = Field(default="en", description="Documentation language")
    generate_docs: bool = Field(default=False, description="Also run DeepWiki wiki generation after indexing")


class SearchProjectParams(BaseModel):
    project_id: str = Field(description="Project identifier (owner/repo)")
    query: str = Field(description="Search query")
    types: Optional[list[str]] = Field(default=None, description="Filter: function, class, module, concept, wikipage")
    limit: int = Field(default=20)


class FindSymbolParams(BaseModel):
    project_id: str
    name: str = Field(description="Symbol name (function, class, variable)")
    type: Optional[str] = Field(default=None, description="function, class, type")


class GetSymbolContextParams(BaseModel):
    project_id: str
    symbol_id: str = Field(description="Graph node ID (elementId)")
    depth: int = Field(default=2, description="Traversal depth for relationships")
    include_docs: bool = Field(default=True)


class GetDependenciesParams(BaseModel):
    project_id: str
    target_id: str = Field(description="Module or symbol node ID")
    direction: str = Field(default="both", description="incoming, outgoing, both")
    max_depth: int = Field(default=3)


class TraceCallPathParams(BaseModel):
    project_id: str
    from_symbol: str
    to_symbol: str
    max_paths: int = Field(default=5)
    max_depth: int = Field(default=10)


class GetImpactAnalysisParams(BaseModel):
    project_id: str
    symbol_id: str
    max_depth: int = Field(default=3)
    include_tests: bool = Field(default=True)


class FindRelatedDocsParams(BaseModel):
    project_id: str
    query: str
    symbol_id: Optional[str] = Field(default=None)
    limit: int = Field(default=10)


class GetTestsForSymbolParams(BaseModel):
    project_id: str
    symbol_id: str
    limit: int = Field(default=20)


class GetGitContextParams(BaseModel):
    project_id: str
    target_id: str = Field(description="File or symbol node ID")
    limit: int = Field(default=10)


class QueryProjectGraphParams(BaseModel):
    project_id: str
    cypher: str = Field(description="Read-only Cypher query")
    params: dict = Field(default_factory=dict)


class GetGraphSchemaParams(BaseModel):
    project_id: str


class GetProjectOverviewParams(BaseModel):
    project_id: str


class GenerateWikiParams(BaseModel):
    project_id: str = Field(description="Project identifier (repo_url or local path)")
    repo_type: str = Field(default="local", description="github, gitlab, bitbucket, local")
    owner: Optional[str] = Field(default=None, description="Owner (derived if omitted)")
    repo: Optional[str] = Field(default=None, description="Repo name (derived if omitted)")
    provider: str = Field(default="nvidia", description="LLM provider (e.g. nvidia, openrouter, google, openai, lmstudio, ollama)")
    model: Optional[str] = Field(default=None, description="Model name for the provider")
    language: str = Field(default="en", description="Documentation language")


class GenerateCodemapParams(BaseModel):
    project_id: str = Field(description="Project identifier (repo_url or local path)")
    question: str = Field(description="How-to / usage question for the codemap")
    repo_type: str = Field(default="local", description="github, gitlab, bitbucket, local")
    provider: str = Field(default="nvidia", description="LLM provider (e.g. nvidia, openrouter, google, openai, lmstudio, ollama)")
    model: Optional[str] = Field(default=None, description="Model name for the provider")
    language: str = Field(default="en", description="Documentation language")


class ListProjectsParams(BaseModel):
    pass


class GetFileSymbolsParams(BaseModel):
    project_id: str
    file_path: str = Field(description="Relative file path (forward-slash)")


class ReadWikiPageParams(BaseModel):
    project_id: str
    title: str = Field(description="Wiki page title (partial match ok)")


class GetEntryPointsParams(BaseModel):
    project_id: str


class GetProjectTreeParams(BaseModel):
    project_id: str
    max_depth: int = Field(default=3, description="Traversal depth for the tree")


class GetJobStatusParams(BaseModel):
    job_id: str = Field(description="Job ID returned by generate_wiki or generate_codemap")


class ViewMindmapParams(BaseModel):
    project_id: Optional[str] = Field(
        default=None,
        description="Project identifier or local path (defaults to latest active project)",
    )
    max_depth: int = Field(default=2, description="Graph traversal depth")


MINDMAP_APP_URI = "ui://mindmap/app.html"

MINDMAP_PANE_META = {
    "ui": {"resourceUri": MINDMAP_APP_URI},
    "com.google.antigravity/ui": {
        "entrypoints": [
            {"type": "aux_pane", "title": "Mindmap Graph"},
            {"type": "global", "title": "Mindmap Graph"},
        ]
    },
}


MCP_TOOLS = [
    Tool(
        name="index_project",
        description="Index a new repository: clone, analyze, generate wiki/codemap, build graph",
        inputSchema=IndexProjectParams.model_json_schema(),
    ),
    Tool(
        name="update_project",
        description="Synchronize changed files since last index",
        inputSchema=IndexProjectParams.model_json_schema(),
    ),
    Tool(
        name="get_project_overview",
        description="High-level architecture summary: modules, entry points, key concepts",
        inputSchema=GetProjectOverviewParams.model_json_schema(),
        meta=MINDMAP_PANE_META,
    ),
    Tool(
        name="search_project",
        description="Search symbols, concepts, and documentation across the project",
        inputSchema=SearchProjectParams.model_json_schema(),
    ),
    Tool(
        name="find_symbol",
        description="Locate a specific function, class, or type by name",
        inputSchema=FindSymbolParams.model_json_schema(),
    ),
    Tool(
        name="get_symbol_context",
        description="Retrieve source code, callers, callees, docs, and tests for a symbol",
        inputSchema=GetSymbolContextParams.model_json_schema(),
    ),
    Tool(
        name="get_dependencies",
        description="Explore module and symbol dependencies (imports, calls, references)",
        inputSchema=GetDependenciesParams.model_json_schema(),
    ),
    Tool(
        name="trace_call_path",
        description="Find call chains between two symbols",
        inputSchema=TraceCallPathParams.model_json_schema(),
    ),
    Tool(
        name="get_impact_analysis",
        description="Determine potentially affected components if a symbol changes",
        inputSchema=GetImpactAnalysisParams.model_json_schema(),
    ),
    Tool(
        name="find_related_docs",
        description="Find relevant wiki pages and documentation for a topic or symbol",
        inputSchema=FindRelatedDocsParams.model_json_schema(),
    ),
    Tool(
        name="get_tests_for_symbol",
        description="Find tests that validate a specific function or class",
        inputSchema=GetTestsForSymbolParams.model_json_schema(),
    ),
    Tool(
        name="get_git_context",
        description="Recent changes, authors, and history for a file or symbol",
        inputSchema=GetGitContextParams.model_json_schema(),
    ),
    Tool(
        name="query_project_graph",
        description="Advanced read-only Cypher query for power users",
        inputSchema=QueryProjectGraphParams.model_json_schema(),
    ),
    Tool(
        name="get_graph_schema",
        description="List available node types, relationships, and properties",
        inputSchema=GetGraphSchemaParams.model_json_schema(),
    ),
    Tool(
        name="generate_wiki",
        description=(
            "Generate DeepWiki documentation for a project and write it to "
            "<repo>/deepwiki/wiki/ (also projected into the graph)"
        ),
        inputSchema=GenerateWikiParams.model_json_schema(),
    ),
    Tool(
        name="generate_codemap",
        description=(
            "Generate a codemap for a how-to/usage question and write it to "
            "<repo>/deepwiki/codemap/ (also projected into the graph). "
            "Returns a job_id — poll with get_job_status."
        ),
        inputSchema=GenerateCodemapParams.model_json_schema(),
    ),
    Tool(
        name="list_projects",
        description="List all projects that have been indexed. Use this first to discover available project_ids.",
        inputSchema=ListProjectsParams.model_json_schema(),
    ),
    Tool(
        name="get_file_symbols",
        description="List all functions, classes, and types defined in a specific file, ordered by line number.",
        inputSchema=GetFileSymbolsParams.model_json_schema(),
    ),
    Tool(
        name="read_wiki_page",
        description="Retrieve full content of a DeepWiki page by title (partial match). No filesystem access needed.",
        inputSchema=ReadWikiPageParams.model_json_schema(),
    ),
    Tool(
        name="get_entry_points",
        description="Find main(), routes, CLI commands, handlers — the execution entry points of the project.",
        inputSchema=GetEntryPointsParams.model_json_schema(),
    ),
    Tool(
        name="get_project_tree",
        description="Return a compact module/file tree for navigating the project structure without filesystem access.",
        inputSchema=GetProjectTreeParams.model_json_schema(),
    ),
    Tool(
        name="get_job_status",
        description="Check the status of an async wiki or codemap generation job by its job_id.",
        inputSchema=GetJobStatusParams.model_json_schema(),
    ),
    Tool(
        name="view_mindmap",
        description="Render an interactive visual knowledge graph of the project in the Antigravity UI pane or browser.",
        inputSchema=ViewMindmapParams.model_json_schema(),
        meta=MINDMAP_PANE_META,
    ),
]