from dataclasses import dataclass
from typing import Optional
from .parser import ParseResult, ImportDef, CallDef
import os


@dataclass
class ResolvedImport:
    from_file: str
    from_module: str
    to_module: str
    to_file: str
    symbols: list[str]


@dataclass
class ResolvedCall:
    caller_file: str
    caller_function: str
    callee_file: str
    callee_function: str
    line: int


class SymbolResolver:
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.module_to_file: dict[str, str] = {}
        self.symbol_index: dict[tuple[str, str], str] = {}

    def build_index(self, parse_results: list[ParseResult]):
        for pr in parse_results:
            module = self._file_to_module(pr.file_path)
            self.module_to_file[module] = pr.file_path
            for fn in pr.functions:
                self.symbol_index[(module, fn.name)] = pr.file_path
            for cl in pr.classes:
                self.symbol_index[(module, cl.name)] = pr.file_path

    def resolve_imports(self, parse_results: list[ParseResult]) -> list[ResolvedImport]:
        resolved = []
        for pr in parse_results:
            from_module = self._file_to_module(pr.file_path)
            for imp in pr.imports:
                target_module = self._resolve_module(imp.module, from_module)
                if target_module and target_module in self.module_to_file:
                    resolved.append(ResolvedImport(
                        from_file=pr.file_path,
                        from_module=from_module,
                        to_module=target_module,
                        to_file=self.module_to_file[target_module],
                        symbols=imp.symbols,
                    ))
        return resolved

    def resolve_calls(self, parse_results: list[ParseResult]) -> list[ResolvedCall]:
        resolved = []
        for pr in parse_results:
            from_module = self._file_to_module(pr.file_path)
            for call in pr.calls:
                target_file = self._resolve_call_target(call.callee, from_module, pr)
                if target_file:
                    resolved.append(ResolvedCall(
                        caller_file=pr.file_path,
                        caller_function=call.caller,
                        callee_file=target_file,
                        callee_function=call.callee,
                        line=call.line,
                    ))
        return resolved

    def _file_to_module(self, file_path: str) -> str:
        rel = os.path.relpath(file_path, self.project_root)
        return rel.replace("/", ".").replace(".py", "").replace(".js", "").replace(".ts", "")

    def _resolve_module(self, import_path: str, from_module: str) -> Optional[str]:
        if import_path.startswith("."):
            parts = from_module.split(".")
            level = len(import_path) - len(import_path.lstrip("."))
            base = ".".join(parts[:-level]) if level < len(parts) else ""
            rest = import_path.lstrip(".")
            return f"{base}.{rest}" if base else rest
        return import_path

    def _resolve_call_target(self, callee: str, from_module: str, parse_result: ParseResult) -> Optional[str]:
        for fn in parse_result.functions:
            if fn.name == callee:
                return parse_result.file_path
        for imp in parse_result.imports:
            if callee in imp.symbols:
                target_module = self._resolve_module(imp.module, from_module)
                return self.module_to_file.get(target_module)
        for (mod, sym), file in self.symbol_index.items():
            if sym == callee:
                return file
        return None