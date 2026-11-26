import pytest
from map.code_intel.parser import CodeParser
from map.code_intel.resolver import SymbolResolver
from map.code_intel.projector import StaticGraphProjector

def test_static_graph_projector():
    parser = CodeParser()
    p1 = parser.parse_file("/tmp/repo/api.py", "def handle():\n    return 'ok'\n")
    resolver = SymbolResolver("/tmp/repo")
    resolver.build_index([p1])
    imports = resolver.resolve_imports([p1])
    calls = resolver.resolve_calls([p1])

    projector = StaticGraphProjector(None)
    batch = projector.project([p1], imports, calls, "dummy_sha", repo_root="/tmp/repo")

    assert len(batch.nodes) > 0
    labels = [n[0] for n in batch.nodes]
    assert "File" in labels
    assert "Function" in labels
    assert "Module" in labels

