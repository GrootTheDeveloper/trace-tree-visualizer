from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ArrayConfig:
    name: str
    structure_type: str
    index_base: int = 1
    size_variable: str = "n"
    role: str = ""
    source_for: str = ""


@dataclass
class OperationConfig:
    function_name: str
    operation_type: str
    target_array: str
    params: list[str] = field(default_factory=list)
    param_roles: dict[str, str] = field(default_factory=dict)
    logical_size: str | None = None


@dataclass
class InstrumentConfig:
    target_arrays: list[ArrayConfig]
    operations: list[OperationConfig]
    watch_expressions: list[str] = field(default_factory=list)
    auto_watch_scalars: bool = True
    timeout_seconds: int = 10
    max_trace_events: int = 100_000
    output_dir: Path = Path("prototype/build/instrumented")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstrumentConfig":
        limits = data.get("limits", {})
        arrays = [ArrayConfig(**item) for item in data.get("target_arrays", [])]
        operations = [OperationConfig(**item) for item in data.get("operations", [])]
        watches = [str(item).strip() for item in data.get("watch_expressions", []) if str(item).strip()]
        return cls(
            target_arrays=arrays,
            operations=operations,
            watch_expressions=watches,
            auto_watch_scalars=bool(data.get("auto_watch_scalars", True)),
            timeout_seconds=int(limits.get("timeout_seconds", 10)),
            max_trace_events=int(limits.get("max_trace_events", 100_000)),
        )

    @classmethod
    def from_json(cls, path: Path) -> "InstrumentConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class LineMapping:
    original_line: int
    instrumented_line: int


@dataclass
class InstrumentResult:
    success: bool
    output_path: Path | None = None
    source_mapping: list[LineMapping] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    mode: str = "regex_fallback"


class Instrumenter:
    _ORIGINAL_LINE_MARKER = "__CP_TRACE_ORIG_LINE__"

    def __init__(self, config: InstrumentConfig):
        self.config = config
        self.array_value_types: dict[str, str] = {}
        self.global_identifiers: set[str] = set()

    def instrument(self, source_path: Path, output_path: Path | None = None) -> InstrumentResult:
        source_path = Path(source_path)
        source = source_path.read_text(encoding="utf-8")
        
        for array in self.config.target_arrays:
            if re.search(rf"\b(?:auto|[A-Za-z_]\w*)\s*&\s*[A-Za-z_]\w*\s*=\s*(?:[A-Za-z_]\w*\s*\.\s*|->\s*)?\b{re.escape(array.name)}\s*\[", source):
                return InstrumentResult(success=False, errors=[f"Lỗi: Không hỗ trợ gán tham chiếu (auto& cur = {array.name}[...]) do giới hạn của Proxy Object. Vui lòng thao tác trực tiếp trên {array.name}[...]."], mode="regex_fallback")

        mode = "libclang" if self._libclang_available() else "regex_fallback"
        try:
            marked_source = self._mark_original_lines(source)
            marked_instrumented = self._instrument_with_regex(marked_source)
            marked_instrumented = self._insert_struct_serializations_after_definitions(marked_instrumented, source)
            instrumented, source_mapping = self._strip_markers_and_build_mapping(marked_instrumented)
        except Exception as exc:
            return InstrumentResult(success=False, errors=[str(exc)], mode=mode)

        if output_path is None:
            self.config.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.config.output_dir / f"{source_path.stem}_instrumented.cpp"
        else:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        Path(output_path).write_text(instrumented, encoding="utf-8")
        return InstrumentResult(
            success=True,
            output_path=Path(output_path),
            source_mapping=source_mapping,
            mode=mode,
        )

    def _mark_original_lines(self, source: str) -> str:
        lines: list[str] = []
        for line_no, line in enumerate(source.splitlines(), start=1):
            lines.append(f"// {self._ORIGINAL_LINE_MARKER}:{line_no}")
            lines.append(line)
        return "\n".join(lines)

    def _strip_markers_and_build_mapping(self, marked_source: str) -> tuple[str, list[LineMapping]]:
        clean_lines: list[str] = []
        mapping: list[LineMapping] = []
        current_original_line = 0
        marker_pattern = re.compile(rf"^\s*//\s*{re.escape(self._ORIGINAL_LINE_MARKER)}:(\d+)\s*$")

        for line in marked_source.splitlines():
            marker = marker_pattern.match(line)
            if marker is not None:
                current_original_line = int(marker.group(1))
                continue
            clean_lines.append(line)
            mapping.append(
                LineMapping(
                    original_line=current_original_line,
                    instrumented_line=len(clean_lines),
                )
            )

        return "\n".join(clean_lines), mapping

    def _libclang_available(self) -> bool:
        try:
            import clang.cindex  # noqa: F401
        except Exception:
            return False
        return True

    def _instrument_with_regex(self, source: str) -> str:
        source = self._preprocess_headers(source)
        self.global_identifiers = self._global_identifiers(source)
        source = self._ensure_trace_include(source)
        source = self._replace_array_declarations(source)
        source = self._replace_vector_parameters(source)
        source = self._replace_target_subscripts(source)
        source = self._insert_operation_scopes(source)
        source = self._insert_watch_points(source)
        source = self._instrument_main(source)
        source = self._instrument_conditions(source)
        source = self._instrument_else_branches(source)
        source = self._insert_source_line_events(source)
        return source

    def _preprocess_headers(self, source: str) -> str:
        replacement = "\n".join(
            [
                "#include <iostream>",
                "#include <vector>",
                "#include <algorithm>",
                "#include <cstring>",
                "#include <cstdio>",
                "#include <cmath>",
                "#include <string>",
                "#include <map>",
                "#include <set>",
                "#include <queue>",
                "#include <stack>",
                "#include <numeric>",
                "#include <functional>",
                "#include <cassert>",
            ]
        )
        return source.replace("#include <bits/stdc++.h>", replacement)

    def _ensure_trace_include(self, source: str) -> str:
        if '#include "trace.hpp"' in source or "#include <trace.hpp>" in source:
            return source
        include = '#include "trace.hpp"\n'
        include_matches = list(re.finditer(r"^\s*#include\s+[<\"].+[>\"]\s*$", source, flags=re.MULTILINE))
        if not include_matches:
            return include + source
        last = include_matches[-1]
        return source[: last.end()] + "\n" + include + source[last.end() :]

    def _replace_array_declarations(self, source: str) -> str:
        for array in self.config.target_arrays:
            source = self._replace_vector_declaration(source, array)
            source = self._replace_c_array_declaration(source, array)
        return source

    def _replace_vector_declaration(self, source: str, array: ArrayConfig) -> str:
        constructed_pattern = re.compile(
            rf"\b(?:std::)?vector\s*<\s*(?P<type>[^>]+?)\s*>\s+{re.escape(array.name)}\s*"
            r"\(\s*(?P<size>[^,\)]+)\s*(?:,\s*(?P<init>[^\)]+))?\)\s*;",
            flags=re.MULTILINE,
        )

        def repl(match: re.Match[str]) -> str:
            value_type = match.group("type").strip()
            self.array_value_types[array.name] = value_type
            size_expr = match.group("size").strip()
            init_expr = (match.group("init") or self._default_initial_value(value_type)).strip()
            return (
                f'cp_trace::TrackedArray<{value_type}> {array.name}'
                f'("{array.name}", {size_expr}, {init_expr}, "{array.structure_type}", {array.index_base});'
            )

        source = constructed_pattern.sub(repl, source)

        declaration_pattern = re.compile(
            rf"^(?P<indent>[ \t]*)(?P<prefix>(?:std::)?vector\s*<\s*(?P<type>[^>]+?)\s*>\s*)(?P<decls>[^;\n]*\b{re.escape(array.name)}\b[^;\n]*)\s*;",
            flags=re.MULTILINE,
        )

        def declaration_repl(match: re.Match[str]) -> str:
            value_type = match.group("type").strip()
            parts = self._split_declarators(match.group("decls"))
            remaining: list[str] = []
            found = False
            for part in parts:
                if re.match(rf"\s*{re.escape(array.name)}\s*(?:$|[({{=])", part):
                    found = True
                else:
                    remaining.append(part.strip())
            if not found:
                return match.group(0)
            self.array_value_types[array.name] = value_type
            indent = match.group("indent")
            prefix = match.group("prefix")
            preserved = f"{indent}{prefix}{', '.join(remaining)};\n" if remaining else ""
            init_expr = self._default_initial_value(value_type)
            return (
                preserved
                + f'{indent}cp_trace::TrackedArray<{value_type}> {array.name}'
                + f'("{array.name}", 0, {init_expr}, "{array.structure_type}", {array.index_base});'
            )

        return declaration_pattern.sub(declaration_repl, source)

    def _replace_c_array_declaration(self, source: str, array: ArrayConfig) -> str:
        type_pattern = r"(?:long\s+long|int|long|short|double|float|char|bool|ll|[A-Za-z_]\w*)"
        statement_pattern = re.compile(
            rf"^(?P<indent>[ \t]*)(?P<prefix>\b{type_pattern}\s+)(?P<decls>[^;\n]*\b{re.escape(array.name)}\s*\[[^\]]+\][^;\n]*)\s*;",
            flags=re.MULTILINE,
        )

        def repl(match: re.Match[str]) -> str:
            value_type = match.group("prefix").strip()
            if self._looks_like_statement_keyword(value_type):
                return match.group(0)
            parts = self._split_declarators(match.group("decls"))
            remaining: list[str] = []
            target_decl: str | None = None
            for part in parts:
                if re.match(rf"\s*{re.escape(array.name)}\s*\[", part):
                    target_decl = part
                else:
                    remaining.append(part.strip())
            if target_decl is None:
                return match.group(0)
            size_match = re.search(rf"\b{re.escape(array.name)}\s*\[\s*(?P<size>[^\]]+)\s*\]", target_decl)
            if size_match is None:
                return match.group(0)
            self.array_value_types[array.name] = value_type
            size_expr = size_match.group("size").strip()
            indent = match.group("indent")
            prefix = match.group("prefix")
            preserved = f"{indent}{prefix}{', '.join(remaining)};\n" if remaining else ""
            init_expr = self._default_initial_value(value_type)
            return (
                preserved +
                f'{indent}cp_trace::TrackedArray<{value_type}> {array.name}'
                f'("{array.name}", {size_expr}, {init_expr}, "{array.structure_type}", {array.index_base});'
            )

        return statement_pattern.sub(repl, source)

    def _looks_like_statement_keyword(self, value_type: str) -> bool:
        return value_type.strip() in {
            "break",
            "case",
            "continue",
            "do",
            "else",
            "for",
            "if",
            "return",
            "switch",
            "while",
        }

    def _default_initial_value(self, value_type: str) -> str:
        normalized = re.sub(r"\s+", " ", value_type.strip())
        numeric_types = {
            "int",
            "long",
            "long long",
            "short",
            "double",
            "float",
            "char",
            "bool",
            "ll",
        }
        if normalized in numeric_types:
            return "0"
        return f"{value_type}{{}}"

    def _split_declarators(self, decls: str) -> list[str]:
        parts: list[str] = []
        depth = 0
        start = 0
        for index, char in enumerate(decls):
            if char in "([{":
                depth += 1
            elif char in ")]}" and depth:
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(decls[start:index].strip())
                start = index + 1
        tail = decls[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def _replace_vector_parameters(self, source: str) -> str:
        for array in self.config.target_arrays:
            pattern = re.compile(
                rf"\b(?:std::)?vector\s*<\s*(?P<type>[^>]+?)\s*>\s*&\s*{re.escape(array.name)}\b"
            )

            def repl(match: re.Match[str]) -> str:
                value_type = match.group("type").strip()
                self.array_value_types[array.name] = value_type
                return f"cp_trace::TrackedArray<{value_type}>& {array.name}"

            source = pattern.sub(repl, source)
        return source

    def _replace_target_subscripts(self, source: str) -> str:
        for array in self.config.target_arrays:
            source = self._parse_and_replace_subscripts(source, array)
        return source

    def _parse_and_replace_subscripts(self, source: str, array: ArrayConfig) -> str:
        import re
        token_pattern = re.compile(
            r'(?P<string>"(?:\\.|[^"\\])*")|'
            r"(?P<char>'(?:\\.|[^'\\])*')|"
            r'(?P<line_comment>//[^\n]*)|'
            r'(?P<block_comment>/\*.*?\*/)',
            re.DOTALL
        )
        
        def update_mask(src: str) -> str:
            masked = list(src)
            for match in token_pattern.finditer(src):
                for i in range(match.start(), match.end()):
                    if masked[i] not in ('\n', '\r'):
                        masked[i] = ' '
            return "".join(masked)
            
        masked_source = update_mask(source)
        
        # F3: Match prefix this-> or obj.
        pattern = re.compile(rf"([A-Za-z_]\w*\s*\.\s*|->\s*)?\b{re.escape(array.name)}\s*\[")
        offset = 0
        while True:
            match = pattern.search(masked_source, offset)
            if not match:
                break
            
            start_bracket = match.end() - 1
            depth = 1
            end_bracket = -1
            for i in range(start_bracket + 1, len(source)):
                if source[i] == '[':
                    depth += 1
                elif source[i] == ']':
                    depth -= 1
                    if depth == 0:
                        end_bracket = i
                        break
                        
            if end_bracket == -1:
                offset = start_bracket + 1
                continue
                
            inner_expr = source[start_bracket + 1 : end_bracket]
            prefix = match.group(1) or ""
            full_name = prefix + array.name
            
            field_pattern = re.compile(r"^\s*\.\s*([A-Za-z_]\w*)")
            field_match = field_pattern.search(masked_source, end_bracket + 1)
            
            if field_match:
                field_name = field_match.group(1)
                replacement = f"CP_TRACE_FIELD_AT({full_name}, {inner_expr}, {field_name})"
                source = source[:match.start()] + replacement + source[field_match.end():]
                masked_source = update_mask(source)
                offset = match.start() + len(replacement)
            else:
                replacement = f"CP_TRACE_AT({full_name}, {inner_expr})"
                source = source[:match.start()] + replacement + source[end_bracket + 1:]
                masked_source = update_mask(source)
                offset = match.start() + len(replacement)
                
        return source

    def _insert_operation_scopes(self, source: str) -> str:
        for operation in self.config.operations:
            array = self._array_for(operation.target_array)
            if array is None:
                continue
            pattern = re.compile(
                rf"(?P<head>(?:[\w:<>,&*\s]+)\b{re.escape(operation.function_name)}\s*\([^;{{}}]*\)\s*)\{{",
                flags=re.MULTILINE,
            )

            def repl(match: re.Match[str]) -> str:
                body = self._scope_lines(operation, array, match.group("head"))
                return match.group("head") + "{\n" + body

            source = pattern.sub(repl, source, count=1)
        return source

    def _scope_lines(self, operation: OperationConfig, array: ArrayConfig, function_head: str | None = None) -> str:
        op_kind = self._operation_kind(operation, array)
        logical_size = self._safe_logical_size(operation.logical_size or array.size_variable, function_head)
        lines = [f'    CP_TRACE_SCOPE("{op_kind}", "{array.name}", {logical_size});']
        emitted_labels: set[str] = set()
        emitted_expressions: set[str] = set()
        for role, expression in operation.param_roles.items():
            if not role or not expression:
                continue
            if not self._param_expression_available(expression, function_head):
                continue
            lines.append(f'    CP_TRACE_PARAM("{self._cpp_string(role)}", {expression});')
            emitted_labels.add(role)
            emitted_expressions.add(str(expression).strip())
        for param in operation.params:
            if param in emitted_labels or param in emitted_expressions:
                continue
            if not self._param_expression_available(param, function_head):
                continue
            lines.append(f'    CP_TRACE_PARAM("{param}", {param});')
        return "\n".join(lines) + "\n"

    def _param_expression_available(self, expression: str, function_head: str | None) -> bool:
        expression = str(expression or "").strip()
        if not expression:
            return False
        identifiers = self._expr_identifiers(expression)
        if not identifiers or function_head is None:
            return True
        params = set(self._function_param_names(function_head))
        available = params | self.global_identifiers
        return all(identifier in available for identifier in identifiers)

    def _safe_logical_size(self, expression: str, function_head: str | None) -> str:
        expression = str(expression or "0").strip() or "0"
        identifiers = self._expr_identifiers(expression)
        if not identifiers or function_head is None:
            return expression
        params = set(self._function_param_names(function_head))
        available = params | self.global_identifiers
        if all(identifier in available for identifier in identifiers):
            return expression
        return "0"

    def _global_identifiers(self, source: str) -> set[str]:
        identifiers: set[str] = set()
        depth = 0
        declaration_pattern = re.compile(
            r"\b(?:const\s+)?(?:unsigned\s+)?(?:long\s+long|long|int|short|double|float|char|bool|string|std::string|[A-Za-z_]\w*)\s+([^;]+);"
        )
        for line in source.splitlines():
            stripped = line.strip()
            if depth == 0:
                for match in declaration_pattern.finditer(stripped):
                    for raw_part in match.group(1).split(","):
                        part = raw_part.split("=", 1)[0].strip()
                        name_match = re.match(r"([A-Za-z_]\w*)", part)
                        if name_match:
                            identifiers.add(name_match.group(1))
            depth += line.count("{") - line.count("}")
            if depth < 0:
                depth = 0
        return identifiers

    def _function_param_names(self, function_head: str) -> list[str]:
        match = re.search(r"\((?P<params>[^()]*)\)\s*$", function_head.strip())
        if match is None:
            return []
        names: list[str] = []
        for raw in self._split_params(match.group("params")):
            part = raw.split("=", 1)[0].strip()
            if not part:
                continue
            part = part.replace("&", " ").replace("*", " ")
            param_match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*$", part)
            if param_match:
                names.append(param_match.group(1))
        return names

    def _split_params(self, params: str) -> list[str]:
        parts: list[str] = []
        depth = 0
        start = 0
        for index, char in enumerate(params):
            if char == "<":
                depth += 1
            elif char == ">" and depth:
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(params[start:index])
                start = index + 1
        parts.append(params[start:])
        return parts

    def _operation_kind(self, operation: OperationConfig, array: ArrayConfig) -> str:
        if array.structure_type == "segment_tree":
            prefix = "segment"
        elif array.structure_type == "fenwick":
            prefix = "fenwick"
        else:
            prefix = array.structure_type
        return f"{prefix}_{operation.operation_type}"

    def _array_for(self, name: str) -> ArrayConfig | None:
        for array in self.config.target_arrays:
            if array.name == name:
                return array
        return None

    def _insert_watch_points(self, source: str) -> str:
        watches = [expr for expr in self.config.watch_expressions if expr]
        if not watches and not self.config.auto_watch_scalars:
            return source

        source_lines = source.splitlines()
        lines: list[str] = []
        in_function = False
        function_depth = 0
        for index, line in enumerate(source_lines):
            lines.append(line)
            stripped = line.strip()
            opens_function = not in_function and self._looks_like_function_opening(stripped)
            if opens_function:
                in_function = True
            emitted: set[str] = set()
            for expr in watches:
                if in_function and self._should_watch_after_line(line, expr, self._next_code_line(source_lines, index)):
                    indent = re.match(r"^(\s*)", line).group(1)
                    if line.strip().endswith("{"):
                        indent += "    "
                    label = self._cpp_string(expr)
                    lines.append(f'{indent}CP_TRACE_WATCH("{label}", {expr});')
                    emitted.add(expr)
            if in_function and self.config.auto_watch_scalars and self._safe_watch_insertion_line(line, self._next_code_line(source_lines, index)):
                for expr in self._auto_watch_expressions_for_line(line):
                    if expr in emitted:
                        continue
                    indent = re.match(r"^(\s*)", line).group(1)
                    label = self._cpp_string(expr)
                    lines.append(f'{indent}CP_TRACE_WATCH("{label}", {expr});')
                    emitted.add(expr)
            if in_function:
                function_depth += line.count("{") - line.count("}")
                if function_depth <= 0:
                    in_function = False
                    function_depth = 0
        return "\n".join(lines)

    def _looks_like_function_opening(self, stripped: str) -> bool:
        if not stripped.endswith("{"):
            return False
        if re.match(r"^(if|else|for|while|switch|catch|do)\b", stripped):
            return False
        return re.match(
            r"^(?:template\s*<[^>]+>\s*)?[\w:<>,&*\s]+\s+[A-Za-z_]\w*\s*\([^;{}]*\)\s*\{$",
            stripped,
        ) is not None

    def _next_code_line(self, lines: list[str], current_index: int) -> str:
        for line in lines[current_index + 1 :]:
            stripped = line.strip()
            if stripped and not stripped.startswith("//"):
                return stripped
        return ""

    def _should_watch_after_line(self, line: str, expr: str, next_line: str = "") -> bool:
        if not self._safe_watch_insertion_line(line, next_line):
            return False
        identifiers = self._expr_identifiers(expr)
        if not identifiers:
            return False
        return all(re.search(rf"\b{re.escape(identifier)}\b", line) for identifier in identifiers)

    def _safe_watch_insertion_line(self, line: str, next_line: str = "") -> bool:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            return False
        if stripped.startswith("CP_TRACE_"):
            return False
        if re.match(r"^(\+|-|\*|/|%|&&|\|\||,|:|\?|\.|->)", stripped):
            return False
        if stripped.startswith("return "):
            return False
        if next_line.startswith("else"):
            return False
        if self._is_single_line_control_statement(stripped):
            return False
        if not (stripped.endswith(";") or stripped.endswith("{")):
            return False
        return True

    def _is_single_line_control_statement(self, stripped: str) -> bool:
        if stripped.endswith("{"):
            return False
        return re.match(r"^(if|else\s+if|else|for|while)\b", stripped) is not None

    def _expr_identifiers(self, expr: str) -> list[str]:
        keywords = {
            "and", "or", "not", "true", "false", "sizeof", "static_cast",
            "int", "long", "short", "double", "float", "char", "bool",
            "string", "vector", "std",
        }
        identifiers: list[str] = []
        for match in re.finditer(r"[A-Za-z_]\w*", expr):
            name = match.group(0)
            if name in keywords:
                continue
            if match.start() > 0 and expr[match.start() - 1] == ".":
                continue
            if name not in identifiers:
                identifiers.append(name)
        return identifiers

    def _auto_watch_expressions_for_line(self, line: str) -> list[str]:
        stripped = line.strip()
        results: list[str] = []
        declaration = re.match(
            r"^(?:const\s+)?(?:unsigned\s+)?(?:long\s+long|long|int|short|double|float|char|bool|string|std::string)\s+([A-Za-z_]\w*)\s*(?:=[^;]*)?;",
            stripped,
        )
        if declaration:
            results.append(declaration.group(1))

        assignment = re.match(r"^([A-Za-z_]\w*)\s*(?:[+\-*/%&|^]?=)\s*[^;]+;", stripped)
        if assignment and assignment.group(1) not in results:
            results.append(assignment.group(1))

        return [name for name in results if name not in {"cin", "cout", "cerr"}]

    def _cpp_string(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _instrument_main(self, source: str) -> str:
        match = re.search(r"\bint\s+main\s*\([^)]*\)\s*\{", source)
        if match is None:
            return source
        open_insert = match.end()
        source = source[:open_insert] + '\n    CP_TRACE_OPEN("trace.jsonl");' + source[open_insert:]

        body_start = open_insert
        body_end = self._find_matching_brace(source, body_start - 1)
        if body_end is None:
            return source
        body = source[body_start:body_end]
        return_match = list(re.finditer(r"\breturn\s+[^;]+;", body))
        if return_match:
            insert_at = body_start + return_match[-1].start()
        else:
            insert_at = body_end
        return source[:insert_at] + "    CP_TRACE_CLOSE();\n" + source[insert_at:]

    def _insert_source_line_events(self, source: str) -> str:
        marker_pattern = re.compile(rf"^\s*//\s*{re.escape(self._ORIGINAL_LINE_MARKER)}:(\d+)\s*$")
        output: list[str] = []
        current_original_line = 0
        in_function = False
        function_depth = 0

        for line in source.splitlines():
            marker = marker_pattern.match(line)
            if marker is not None:
                current_original_line = int(marker.group(1))
                output.append(line)
                continue

            stripped = line.strip()
            opens_function = not in_function and self._looks_like_function_opening(stripped)
            if in_function and self._should_emit_source_line_event(stripped, current_original_line):
                indent = re.match(r"^(\s*)", line).group(1)
                kind = self._source_line_event_kind(stripped)
                output.append(f'{indent}CP_TRACE_LINE({current_original_line}, "{kind}");')

            output.append(line)

            if opens_function:
                in_function = True
                function_depth = line.count("{") - line.count("}")
            elif in_function:
                function_depth += line.count("{") - line.count("}")
            if in_function and function_depth <= 0:
                in_function = False
                function_depth = 0

        return "\n".join(output)

    def _instrument_conditions(self, source: str) -> str:
        marker_pattern = re.compile(rf"^\s*//\s*{re.escape(self._ORIGINAL_LINE_MARKER)}:(\d+)\s*$")
        output: list[str] = []
        current_original_line = 0

        for line in source.splitlines():
            marker = marker_pattern.match(line)
            if marker is not None:
                current_original_line = int(marker.group(1))
                output.append(line)
                continue
            output.append(self._instrument_condition_line(line, current_original_line))

        return "\n".join(output)

    def _instrument_else_branches(self, source: str) -> str:
        marker_pattern = re.compile(rf"^\s*//\s*{re.escape(self._ORIGINAL_LINE_MARKER)}:(\d+)\s*$")
        output: list[str] = []
        current_original_line = 0

        for line in source.splitlines():
            marker = marker_pattern.match(line)
            if marker is not None:
                current_original_line = int(marker.group(1))
                output.append(line)
                continue
            output.append(self._instrument_else_line(line, current_original_line))

        return "\n".join(output)

    def _instrument_else_line(self, line: str, original_line: int) -> str:
        if original_line <= 0 or "CP_TRACE_" in line:
            return line
        match = re.match(r"^(?P<indent>\s*)(?P<prefix>\}\s*)?else(?P<body>\s+.*|\s*)$", line)
        if match is None:
            return line

        indent = match.group("indent")
        prefix = match.group("prefix") or ""
        body = match.group("body") or ""
        body_stripped = body.strip()
        trace = f'CP_TRACE_LINE({original_line}, "else");'

        if body_stripped.startswith("if"):
            instrumented_if = self._instrument_condition_line(indent + body_stripped, original_line).strip()
            return f"{indent}{prefix}else {instrumented_if}"
        if body_stripped.startswith("{"):
            tail = body[body.find("{") + 1 :]
            return f"{indent}{prefix}else {{{trace}{tail}"
        if body_stripped and body_stripped.endswith(";"):
            return f"{indent}{prefix}else {{ {trace} {body_stripped} }}"
        return line

    def _instrument_condition_line(self, line: str, original_line: int) -> str:
        if original_line <= 0:
            return line
        stripped = line.strip()
        if not stripped or stripped.startswith("CP_TRACE_") or "CP_TRACE_COND(" in stripped:
            return line
        if stripped.startswith("else") or stripped.startswith("} else"):
            return line
        match = re.match(r"^(?P<indent>\s*)(?P<keyword>if|while)\s*\(", line)
        if match is None:
            return line
        open_pos = match.end() - 1
        close_pos = self._find_matching_paren(line, open_pos)
        if close_pos is None:
            return line
        condition = line[open_pos + 1 : close_pos].strip()
        if not condition or ";" in condition or "CP_TRACE_" in condition:
            return line
        keyword = match.group("keyword")
        tail = line[close_pos + 1 :]
        return f'{match.group("indent")}{keyword} (CP_TRACE_COND({original_line}, ({condition}))){tail}'

    def _find_matching_paren(self, line: str, open_pos: int) -> int | None:
        depth = 0
        for index in range(open_pos, len(line)):
            char = line[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        return None

    def _should_emit_source_line_event(self, stripped: str, original_line: int) -> bool:
        if original_line <= 0:
            return False
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            return False
        if stripped.startswith("CP_TRACE_"):
            return False
        if stripped.startswith("else") or stripped.startswith("} else"):
            return False
        if "CP_TRACE_COND(" in stripped:
            return False
        if re.match(r"^(\+|-|\*|/|%|&&|\|\||,|:|\?|\.|->)", stripped):
            return False
        if stripped in {"{", "}", "};"}:
            return False
        if stripped.startswith("return "):
            return False
        if stripped.startswith("else") or stripped.startswith("} else"):
            return False
        if re.match(r"^(case|default)\b", stripped):
            return False
        if self._looks_like_function_opening(stripped):
            return False
        return stripped.endswith(";") or stripped.endswith("{")

    def _source_line_event_kind(self, stripped: str) -> str:
        if re.match(r"^(if|while|for|switch)\b", stripped):
            return "condition"
        if re.search(r"\b[A-Za-z_]\w*\s*\(", stripped) and stripped.endswith(";"):
            return "call"
        return "statement"

    def _find_matching_brace(self, source: str, open_pos: int) -> int | None:
        depth = 0
        for pos in range(open_pos, len(source)):
            char = source[pos]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return pos
        return None

    def _strip_braces(self, text: str) -> str:
        while True:
            pos = text.find("{")
            if pos == -1:
                break
            brace_count = 1
            end_pos = -1
            for i in range(pos + 1, len(text)):
                if text[i] == "{":
                    brace_count += 1
                elif text[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i
                        break
            if end_pos != -1:
                text = text[:pos] + text[end_pos + 1:]
            else:
                text = text[:pos]
                break
        return text

    def _struct_serialization_overloads(self, source: str) -> list[tuple[str, str]]:
        pattern = re.compile(r'\b(struct|class)\s+(?P<name>[A-Za-z_]\w*)\s*\{')
        overloads: list[tuple[str, str]] = []
        for match in pattern.finditer(source):
            struct_name = match.group("name")
            opening_brace_pos = match.start("name") + len(struct_name)
            while opening_brace_pos < len(source) and source[opening_brace_pos] != "{":
                opening_brace_pos += 1
            if opening_brace_pos >= len(source):
                continue
            closing_brace_pos = self._find_matching_brace(source, opening_brace_pos)
            if closing_brace_pos is None or closing_brace_pos == -1:
                continue
            body = source[opening_brace_pos + 1 : closing_brace_pos]
            body = re.sub(r'//.*', '', body)
            body = re.sub(r'/\*.*?\*/', '', body, flags=re.DOTALL)
            cleaned_body = self._strip_braces(body)
            fields = []
            statements = cleaned_body.split(";")
            keywords = {"const", "static", "volatile", "mutable", "friend", "inline", "virtual", "public", "private", "protected"}
            for stmt in statements:
                stmt = stmt.strip()
                if not stmt:
                    continue
                if "(" in stmt or ")" in stmt or "using" in stmt or "typedef" in stmt:
                    continue
                parts = stmt.split(",")
                first_tokens = parts[0].split()
                if not first_tokens:
                    continue
                first_name = first_tokens[-1].strip("*,& ")
                first_name = re.sub(r'=.*$', '', first_name).strip()
                first_name = re.sub(r'\(.*$', '', first_name).strip()
                if re.match(r'^[A-Za-z_]\w*$', first_name) and first_name not in keywords and "TrackedArray" not in parts[0] and "vector" not in parts[0]:
                    fields.append(first_name)
                for part in parts[1:]:
                    tokens = part.split()
                    if not tokens:
                        continue
                    name = tokens[0].strip("*,& ")
                    name = re.sub(r'=.*$', '', name).strip()
                    name = re.sub(r'\(.*$', '', name).strip()
                    if re.match(r'^[A-Za-z_]\w*$', name) and name not in keywords and "TrackedArray" not in part and "vector" not in part:
                        fields.append(name)
            if fields:
                stream_exprs = []
                for idx, f in enumerate(fields):
                    prefix = "," if idx > 0 else ""
                    stream_exprs.append(f'os << "{prefix}\\\"{f}\\\":" << val.{f};')
                stream_code = "\n    ".join(stream_exprs)
                overload = f"""
inline std::ostream& operator<<(std::ostream& os, const {struct_name}& val) {{
    os << "{{";
    {stream_code}
    os << "}}";
    return os;
}}
"""
            # Check existing operator<<
            if re.search(rf"operator\s*<<\s*\(\s*(?:std::)?ostream\s*&\s*[^,]+,\s*(?:const\s+)?{re.escape(struct_name)}\s*&", source):
                continue
                overloads.append((struct_name, overload))
        return overloads

    def _insert_struct_serializations_after_definitions(self, marked_source: str, original_source: str) -> str:
        overloads = self._struct_serialization_overloads(original_source)
        if not overloads:
            return marked_source
        result = marked_source
        offset = 0
        for struct_name, overload in overloads:
            pattern = re.compile(rf'\b(struct|class)\s+{re.escape(struct_name)}\s*\{{')
            match = pattern.search(result, offset)
            if match is None:
                continue
            opening_brace_pos = result.find("{", match.start())
            closing_brace_pos = self._find_matching_brace(result, opening_brace_pos)
            if closing_brace_pos is None or closing_brace_pos == -1:
                continue
            insert_pos = closing_brace_pos + 1
            while insert_pos < len(result) and result[insert_pos].isspace():
                insert_pos += 1
            if insert_pos < len(result) and result[insert_pos] == ";":
                insert_pos += 1
            insertion = f"\n// {self._ORIGINAL_LINE_MARKER}:0\n{overload}\n"
            result = result[:insert_pos] + insertion + result[insert_pos:]
            offset = insert_pos + len(insertion)
        return result




def load_config(path: Path) -> InstrumentConfig:
    return InstrumentConfig.from_json(path)
