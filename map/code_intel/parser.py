from tree_sitter import Language, Parser, Node, Query, QueryCursor
from dataclasses import dataclass, field
from typing import Optional
import os

try:
    import tree_sitter_python as tsp
    import tree_sitter_javascript as tsjs
    import tree_sitter_typescript as tst
    import tree_sitter_go as tsg
    import tree_sitter_rust as tsr
    import tree_sitter_java as tsj
    import tree_sitter_cpp as tscpp
    HAS_LANGUAGES = True
except ImportError:
    HAS_LANGUAGES = False

SUPPORTED_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
}

def _get_language(lang_name: str):
    if not HAS_LANGUAGES:
        return None
    mapping = {
        "python": tsp.language(),
        "javascript": tsjs.language(),
        "typescript": tst.language_typescript(),
        "tsx": tst.language_tsx(),
        "go": tsg.language(),
        "rust": tsr.language(),
        "java": tsj.language(),
        "cpp": tscpp.language(),
    }
    return mapping.get(lang_name)

@dataclass
class FunctionDef:
    name: str
    signature: str
    start_line: int
    end_line: int
    docstring: str = ""
    node: Node = None

@dataclass
class ClassDef:
    name: str
    file_path: str
    start_line: int
    end_line: int
    docstring: str = ""
    methods: list[str] = field(default_factory=list)
    node: Node = None

@dataclass
class ImportDef:
    module: str
    symbols: list[str]
    line: int
    is_from: bool = False

@dataclass
class CallDef:
    caller: str
    callee: str
    line: int
    node: Node = None

@dataclass
class ParseResult:
    file_path: str
    language: str
    functions: list[FunctionDef] = field(default_factory=list)
    classes: list[ClassDef] = field(default_factory=list)
    imports: list[ImportDef] = field(default_factory=list)
    calls: list[CallDef] = field(default_factory=list)

class CodeParser:
    def __init__(self):
        self.parsers = {}
        for ext, lang in SUPPORTED_LANGUAGES.items():
            try:
                language_fn = _get_language(lang)
                if language_fn:
                    self.parsers[ext] = Parser(Language(language_fn))
            except Exception as e:
                print(f"Warning: Could not load parser for {lang}: {e}")

    def parse_file(self, file_path: str, content: str) -> ParseResult:
        ext = os.path.splitext(file_path)[1]
        parser = self.parsers.get(ext)
        if not parser:
            return ParseResult(file_path=file_path, language="unknown")

        tree = parser.parse(bytes(content, "utf8"))
        language = SUPPORTED_LANGUAGES[ext]

        result = ParseResult(file_path=file_path, language=language)
        queries = self._get_queries(language)

        for name, query in queries.items():
            if query is None:
                continue
            cursor = QueryCursor(query)
            for _pattern_index, captures in cursor.matches(tree.root_node):
                match = {k: v[0] for k, v in captures.items() if v}
                if name == "functions":
                    fn = self._extract_function(match, content, language)
                    if fn:
                        result.functions.append(fn)
                elif name == "classes":
                    cl = self._extract_class(match, content, language)
                    if cl:
                        result.classes.append(cl)
                elif name == "imports":
                    imp = self._extract_import(match, content, language)
                    if imp:
                        result.imports.append(imp)
                elif name == "calls":
                    call = self._extract_call(match, content, language)
                    if call:
                        result.calls.append(call)

        if any(not c.caller for c in result.calls):
            for call in result.calls:
                if call.caller:
                    continue
                for fn in result.functions:
                    if fn.start_line <= call.line <= fn.end_line:
                        call.caller = fn.name
                        break

        return result

    def _get_queries(self, language: str) -> dict:
        return INLINE_QUERIES.get(language, {})

    def _extract_function(self, match, content: str, language: str) -> FunctionDef | None:
        captures = dict(match)
        name_node = captures.get("function.name")
        body_node = captures.get("function.body")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte]
        start_line = name_node.start_point[0] + 1
        end_line = body_node.end_point[0] + 1 if body_node else start_line
        signature = self._get_signature(name_node, body_node, content, language)
        docstring = self._get_docstring(body_node, content, language) if body_node else ""
        return FunctionDef(
            name=name,
            signature=signature,
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
        )

    def _extract_class(self, match, content: str, language: str) -> ClassDef | None:
        captures = dict(match)
        name_node = captures.get("class.name")
        body_node = captures.get("class.body")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte]
        start_line = name_node.start_point[0] + 1
        end_line = body_node.end_point[0] + 1 if body_node else start_line
        docstring = self._get_docstring(body_node, content, language) if body_node else ""
        methods = self._get_methods(body_node, content, language) if body_node else []
        return ClassDef(
            name=name,
            file_path="",
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            methods=methods,
        )

    def _extract_import(self, match, content: str, language: str) -> ImportDef | None:
        captures = dict(match)
        module_node = captures.get("import.module")
        symbols_node = captures.get("import.symbols")
        if not module_node:
            return None
        module = content[module_node.start_byte:module_node.end_byte]
        symbols = []
        if symbols_node:
            symbols_text = content[symbols_node.start_byte:symbols_node.end_byte]
            symbols = [s.strip() for s in symbols_text.split(",")]
        return ImportDef(
            module=module,
            symbols=symbols,
            line=module_node.start_point[0] + 1,
        )

    def _extract_call(self, match, content: str, language: str) -> CallDef | None:
        captures = dict(match)
        caller_node = captures.get("call.caller")
        callee_node = captures.get("call.callee")
        if not callee_node:
            return None
        callee = content[callee_node.start_byte:callee_node.end_byte]
        caller = content[caller_node.start_byte:caller_node.end_byte] if caller_node else ""
        return CallDef(
            caller=caller,
            callee=callee,
            line=callee_node.start_point[0] + 1,
        )

    def _get_signature(self, name_node, body_node, content: str, language: str) -> str:
        if language == "python":
            return content[name_node.start_byte:body_node.start_byte].strip() + ":"
        return content[name_node.start_byte:min(name_node.end_byte + 50, len(content))].strip()

    def _get_docstring(self, body_node, content: str, language: str) -> str:
        if language == "python" and body_node.children:
            first = body_node.children[0]
            if first.type == "expression_statement" and first.children:
                expr = first.children[0]
                if expr.type == "string":
                    return content[expr.start_byte:expr.end_byte].strip('"')
        return ""

    def _get_methods(self, body_node, content: str, language: str) -> list[str]:
        methods = []
        if language == "python":
            for child in body_node.children:
                if child.type == "function_definition":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        methods.append(content[name_node.start_byte:name_node.end_byte])
        return methods


def _make_query(lang_name: str, query_str: str):
    lang_fn = _get_language(lang_name)
    if lang_fn:
        try:
            return Query(Language(lang_fn), query_str)
        except Exception:
            return None
    return None

INLINE_QUERIES = {
    "python": {
        "functions": _make_query("python", """
            (function_definition name: (identifier) @function.name body: (block) @function.body) @function.def
        """),
        "classes": _make_query("python", """
            (class_definition name: (identifier) @class.name body: (block) @class.body) @class.def
        """),
        "imports": _make_query("python", """
            (import_statement name: (dotted_name) @import.module) @import
            (import_from_statement module_name: (dotted_name) @import.module name: (dotted_name) @import.symbols) @import
        """),
        "calls": _make_query("python", """
            (call function: (identifier) @call.callee) @call
        """),
    },
    "javascript": {
        "functions": _make_query("javascript", """
            (function_declaration name: (identifier) @function.name body: (statement_block) @function.body) @function.def
            (arrow_function body: (statement_block) @function.body) @function.def
        """),
        "classes": _make_query("javascript", """
            (class_declaration name: (identifier) @class.name body: (class_body) @class.body) @class.def
        """),
        "imports": _make_query("javascript", """
            (import_statement source: (string) @import.module) @import
        """),
        "calls": _make_query("javascript", """
            (call_expression function: (identifier) @call.callee) @call
        """),
    },
    "typescript": {
        "functions": _make_query("typescript", """
            (function_declaration name: (identifier) @function.name body: (statement_block) @function.body) @function.def
            (arrow_function body: (statement_block) @function.body) @function.def
        """),
        "classes": _make_query("typescript", """
            (class_declaration name: (type_identifier) @class.name body: (class_body) @class.body) @class.def
        """),
        "imports": _make_query("typescript", """
            (import_statement source: (string) @import.module) @import
        """),
        "calls": _make_query("typescript", """
            (call_expression function: (identifier) @call.callee) @call
        """),
    },
    "go": {
        "functions": _make_query("go", """
            (function_declaration name: (identifier) @function.name body: (block) @function.body) @function.def
        """),
        "classes": _make_query("go", """
            (type_declaration (type_spec name: (type_identifier) @class.name type: (struct_type) @class.body)) @class.def
        """),
        "imports": _make_query("go", """
            (import_declaration (import_spec path: (interpreted_string_literal) @import.module)) @import
        """),
        "calls": _make_query("go", """
            (call_expression function: (identifier) @call.callee) @call
        """),
    },
    "rust": {
        "functions": _make_query("rust", """
            (function_item name: (identifier) @function.name body: (block) @function.body) @function.def
        """),
        "classes": _make_query("rust", """
            (struct_item name: (type_identifier) @class.name body: (field_declaration_list) @class.body) @class.def
            (impl_item type: (type_identifier) @class.name) @class.def
        """),
        "imports": _make_query("rust", """
            (use_declaration argument: (use_list) @import.module) @import
            (use_declaration argument: (use_as) @import.module) @import
        """),
        "calls": _make_query("rust", """
            (call_expression function: (scoped_identifier) @call.callee) @call
            (call_expression function: (identifier) @call.callee) @call
        """),
    },
    "java": {
        "functions": _make_query("java", """
            (method_declaration name: (identifier) @function.name body: (block) @function.body) @function.def
        """),
        "classes": _make_query("java", """
            (class_declaration name: (identifier) @class.name body: (class_body) @class.body) @class.def
            (interface_declaration name: (identifier) @class.name body: (interface_body) @class.body) @class.def
        """),
        "imports": _make_query("java", """
            (import_declaration name: (scoped_identifier) @import.module) @import
        """),
        "calls": _make_query("java", """
            (method_invocation name: (identifier) @call.callee) @call
        """),
    },
    "cpp": {
        "functions": _make_query("cpp", """
            (function_definition declarator: (function_declarator declarator: (identifier) @function.name) body: (compound_statement) @function.body) @function.def
        """),
        "classes": _make_query("cpp", """
            (class_specifier name: (type_identifier) @class.name body: (field_declaration_list) @class.body) @class.def
        """),
        "imports": _make_query("cpp", """
            (preproc_include path: (string_literal) @import.module) @import
        """),
        "calls": _make_query("cpp", """
            (call_expression function: (field_expression field: (field_identifier) @call.callee)) @call
            (call_expression function: (identifier) @call.callee) @call
        """),
    },
}