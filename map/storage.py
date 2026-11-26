"""Project-local artifact storage for mindmap.

Convention (per project working directory):

    <repo>/
    ├── deepwiki/          # human-readable docs, written on demand
    │   ├── wiki/*.md
    │   └── codemap/*.md
    └── .mindmap/          # agent-facing machine artifacts (gitignored)
        ├── graph.rl       # Relate property graph
        └── manifest.json  # repo metadata + index stats

A small global registry (~/.adalflow/mindmap/registry.json) maps
``project_id -> repo_path`` so the MCP server can resolve per-project
graphs for remote repositories whose clone lives under ~/.adalflow/repo.
"""

import json
import os
import re
from pathlib import Path

MINDMAP_DIRNAME = ".mindmap"
DEEPWIKI_DIRNAME = "deepwiki"
GRAPH_FILENAME = "graph.rl"
MANIFEST_FILENAME = "manifest.json"


def mindmap_home() -> Path:
    root = Path(
        os.environ.get("MINDMAP_HOME", str(Path.home() / ".adalflow" / "mindmap"))
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def normalize_path(path: str) -> str:
    """Expand ``~`` and resolve symlinks so ``/tmp`` and ``/private/tmp`` match."""
    if not path:
        return path
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def canonical_project_id(project_id: str) -> str:
    """Canonical identity for a project.

    Local directories are resolved to a real absolute path (so trailing
    slashes, ``~``, and macOS ``/tmp`` vs ``/private/tmp`` all collapse to the
    same key). URLs are returned with any trailing slash removed.
    """
    if not project_id:
        return project_id
    expanded = os.path.expanduser(project_id)
    if os.path.isdir(expanded):
        return normalize_path(expanded)
    return project_id.rstrip("/")



def _registry_path() -> Path:
    return mindmap_home() / "registry.json"


def load_registry() -> dict[str, str]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_registry(registry: dict[str, str]) -> None:
    _registry_path().write_text(
        json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8"
    )


def register_project(project_id: str, repo_path: str) -> None:
    registry = load_registry()
    registry[canonical_project_id(project_id)] = normalize_path(repo_path)
    save_registry(registry)


def repo_path_for(project_id: str) -> str | None:
    """Resolve a project_id to its working directory."""
    if not project_id:
        return None
    registry = load_registry()
    key = canonical_project_id(project_id)
    if key in registry:
        path = registry[key]
        if os.path.isdir(path):
            return path
    if os.path.isdir(os.path.expanduser(project_id)):
        return normalize_path(project_id)
    return None


def mindmap_dir(repo_path: str, create: bool = True) -> str:
    path = os.path.join(repo_path, MINDMAP_DIRNAME)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def graph_path_for(repo_path: str, create: bool = True) -> str:
    return os.path.join(mindmap_dir(repo_path, create=create), GRAPH_FILENAME)


def manifest_path_for(repo_path: str) -> str:
    return os.path.join(mindmap_dir(repo_path), MANIFEST_FILENAME)


def write_manifest(repo_path: str, data: dict) -> str:
    path = manifest_path_for(repo_path)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, default=str)
    return path


def read_manifest(repo_path: str) -> dict:
    path = manifest_path_for(repo_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {}


def deepwiki_dir(repo_path: str, create: bool = True) -> str:
    path = os.path.join(repo_path, DEEPWIKI_DIRNAME)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def ensure_gitignore(repo_path: str, entries: tuple[str, ...] = (".mindmap/",)) -> None:
    path = os.path.join(repo_path, ".gitignore")
    existing: list[str] = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                existing = fp.read().splitlines()
        except Exception:
            existing = []
    normalized = {line.strip() for line in existing}
    to_add = [e for e in entries if e not in normalized]
    if not to_add:
        return
    with open(path, "a", encoding="utf-8") as fp:
        if existing and existing[-1].strip() != "":
            fp.write("\n")
        fp.write("\n".join(to_add) + "\n")


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")
    return name or "untitled"


def export_wiki_markdown(repo_path: str, pages: dict) -> list[str]:
    """Write wiki pages as markdown under <repo>/deepwiki/wiki/."""
    out_dir = os.path.join(deepwiki_dir(repo_path), "wiki")
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    for page_id, page in (pages or {}).items():
        title = getattr(page, "title", None) or str(page_id)
        content = getattr(page, "content", "") or ""
        filename = f"{_safe_name(page_id)}-{_safe_name(title)}.md"
        path = os.path.join(out_dir, filename)
        body = f"# {title}\n\n{content}\n"
        file_paths = getattr(page, "filePaths", None) or getattr(page, "file_paths", None)
        if file_paths:
            body += "\n**Files:**\n" + "\n".join(f"- `{p}`" for p in file_paths) + "\n"
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(body)
        written.append(path)
    return written


def export_codemap_markdown(repo_path: str, codemap) -> list[str]:
    """Write a codemap as markdown under <repo>/deepwiki/codemap/."""
    out_dir = os.path.join(deepwiki_dir(repo_path), "codemap")
    os.makedirs(out_dir, exist_ok=True)
    title = getattr(codemap, "title", None) or "codemap"
    path = os.path.join(out_dir, f"{_safe_name(title)}.md")

    lines = [f"# {title}", ""]
    summary = getattr(codemap, "summary", "")
    if summary:
        lines += [summary, ""]
    for section in getattr(codemap, "sections", []) or []:
        sec_title = getattr(section, "title", "") or ""
        lines.append(f"## {sec_title}")
        guide = getattr(section, "guide", "")
        if guide:
            lines += ["", guide]
        lines.append("")
        for step in getattr(section, "steps", []) or []:
            label = getattr(step, "label", "") or getattr(step, "description", "")
            lines.append(f"- **{label}**")
            citation = getattr(step, "citation", None)
            if citation is not None:
                fp = getattr(citation, "file_path", "")
                start = getattr(citation, "start_line", "")
                end = getattr(citation, "end_line", "")
                if fp:
                    lines.append(f"  - `{fp}:{start}-{end}`")
        lines.append("")

    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))
    return [path]
