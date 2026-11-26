NODE_LABELS = {
    "Project": [
        "name",
        "repo_url",
        "project_key",
        "branch",
        "head_sha",
        "indexed_at",
        "provider",
        "model",
        "last_wiki_sha",
    ],
    "Module": ["name", "language", "path", "file_count"],
    "File": ["path", "hash", "language", "size", "lines", "module", "is_entrypoint"],
    "Function": [
        "name",
        "signature",
        "start_line",
        "end_line",
        "docstring",
        "file_path",
        "is_async",
        "is_exported",
    ],
    "Class": [
        "name",
        "file_path",
        "start_line",
        "end_line",
        "docstring",
        "methods",
    ],
    "Concept": ["name", "description", "source", "wiki_page_ids"],
    "WikiPage": ["title", "content", "content_hash", "file_path", "source", "language", "section_id"],
    "Test": ["name", "framework", "file_path", "target_symbol", "target_type"],
    "Commit": ["sha", "author", "timestamp", "message", "files_changed"],
    "Dependency": ["package", "version", "scope", "language"],
}

RELATIONSHIPS = {
    "CONTAINS": {
        "from": ["Project", "Module", "File"],
        "to": ["Module", "File", "Function", "Class"],
    },
    "IMPORTS": {
        "from": ["Module", "File"],
        "to": ["Module", "File"],
        "props": ["symbols", "confidence"],
    },
    "CALLS": {
        "from": ["Function"],
        "to": ["Function"],
        "props": ["line", "resolved", "confidence"],
    },
    "DEFINES": {"from": ["File"], "to": ["Function", "Class"], "props": []},
    "EXPORTS": {
        "from": ["Module", "File"],
        "to": ["Function", "Class"],
        "props": ["export_type"],
    },
    "REFERENCES": {
        "from": ["Function", "Class"],
        "to": ["Function", "Class"],
        "props": ["context"],
    },
    "DOCUMENTS": {
        "from": ["WikiPage"],
        "to": ["Function", "Class", "Module", "Concept"],
        "props": ["excerpt"],
    },
    "TESTS": {
        "from": ["Test"],
        "to": ["Function", "Class"],
        "props": ["test_type"],
    },
    "DEPENDS_ON": {
        "from": ["Module", "Function"],
        "to": ["Module", "Function"],
        "props": ["dep_type"],
    },
    "CHANGED_IN": {
        "from": ["File", "Function", "Class"],
        "to": ["Commit"],
        "props": ["change_type"],
    },
    "RELATED_TO": {
        "from": ["Concept"],
        "to": ["Concept", "Function", "Class"],
        "props": ["relation"],
    },
    "IMPLEMENTS": {
        "from": ["Function", "Class"],
        "to": ["Concept"],
        "props": ["completeness"],
    },
}

PROVENANCE_PROPS = {
    "source": "static_analysis | deepwiki_wiki | deepwiki_codemap | git_history | rag_retrieval",
    "extraction_method": "tree_sitter | llm_structure | llm_page | llm_codemap | git_diff",
    "confidence": "float 0.0-1.0",
    "source_revision": "git_sha",
    "extracted_at": "ISO8601 timestamp",
    "extractor_version": "string",
}

DDL_STATEMENTS = [
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.repo_url IS UNIQUE",
    "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
    "CREATE INDEX function_name IF NOT EXISTS FOR (fn:Function) ON (fn.name)",
    "CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name)",
    "CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name)",
    "CREATE INDEX wiki_page_title IF NOT EXISTS FOR (w:WikiPage) ON (w.title)",
    "CREATE INDEX commit_sha IF NOT EXISTS FOR (c:Commit) ON (c.sha)",
    "CREATE INDEX module_path IF NOT EXISTS FOR (m:Module) ON (m.path)",
    "CREATE INDEX function_signature IF NOT EXISTS FOR (fn:Function) ON (fn.signature)",
]

UNIQUE_KEYS = {
    "Project": "repo_url",
    "Module": "path",
    "File": "path",
    "Function": ("file_path", "signature"),
    "Class": ("file_path", "name"),
    "WikiPage": "title",
    "Commit": "sha",
    "Dependency": "package",
    "Concept": "name",
    "Test": "name",
}
