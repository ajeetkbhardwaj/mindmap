import pytest
from map.code_intel.parser import CodeParser
from map.code_intel.resolver import SymbolResolver

def test_symbol_resolution():
    parser = CodeParser()
    f1_code = "from helper import format_text\n\ndef main():\n    return format_text('hello')\n"
    f2_code = "def format_text(s: str):\n    return s.upper()\n"

    p1 = parser.parse_file("/tmp/fake_repo/main.py", f1_code)
    p2 = parser.parse_file("/tmp/fake_repo/helper.py", f2_code)

    resolver = SymbolResolver("/tmp/fake_repo")
    resolver.build_index([p1, p2])

    imports = resolver.resolve_imports([p1, p2])
    assert len(imports) >= 1
    assert imports[0].to_file == "/tmp/fake_repo/helper.py"

    calls = resolver.resolve_calls([p1, p2])
    assert len(calls) >= 1
    assert calls[0].caller_function == "main"
    assert calls[0].callee_function == "format_text"

