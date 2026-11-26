import pytest
from map.code_intel.parser import CodeParser

def test_python_parsing():
    parser = CodeParser()
    code = """
def calculate_sum(a: int, b: int) -> int:
    \"\"\"Calculates sum of two numbers.\"\"\"
    return a + b

class MathService:
    \"\"\"Math utilities.\"\"\"
    def multiply(self, x, y):
        return x * y
"""
    result = parser.parse_file("math_utils.py", code)
    assert result.language == "python"
    assert len(result.functions) >= 1
    fn = [f for f in result.functions if f.name == "calculate_sum"][0]
    assert "sum" in fn.docstring.lower()
    assert fn.start_line > 0

    assert len(result.classes) == 1
    assert result.classes[0].name == "MathService"

def test_unknown_language():
    parser = CodeParser()
    result = parser.parse_file("notes.txt", "Hello world")
    assert result.language == "unknown"

