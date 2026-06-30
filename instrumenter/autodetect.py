from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .segment_ast import SegmentAstInference, infer_segment_tree_roles


@dataclass
class FunctionDef:
    name: str
    params: list[str]
    body: str


def detect_config(source: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Infer a conservative trace config from a single-file C++ program."""
    overrides = overrides or {}
    clean = _strip_comments(source)
    functions = _functions(clean)
    declarations = _array_declarations(clean)
    subscript_names = _subscript_names(clean)
    segment_ast = infer_segment_tree_roles(source)
    structure = "segment_tree" if segment_ast.functions else _detect_structure(clean, functions)
    array_name = segment_ast.target_array or _choose_array(clean, declarations, subscript_names, structure)
    raw_tree_arrays = (
        _detect_segment_tree_arrays(clean, functions, declarations, subscript_names, segment_ast, array_name)
        if structure == "segment_tree"
        else [array_name]
    )
    tree_arrays, grouped_field_arrays = (
        _group_parallel_field_arrays(functions, raw_tree_arrays)
        if structure == "segment_tree"
        else (raw_tree_arrays, {})
    )
    array_name = tree_arrays[0] if tree_arrays else array_name
    size_variable = _detect_size_variable(clean, declarations.get(array_name, ""), functions)
    index_base = (
        1
        if structure == "fenwick"
        else segment_ast.index_base
        if structure == "segment_tree" and segment_ast.index_base is not None
        else _detect_segment_index_base(clean)
        if structure == "segment_tree"
        else 0
    )
    node_variable = (
        segment_ast.node_variable
        or (_detect_node_variable(functions) if structure == "segment_tree" else "i")
    )
    operations: list[dict[str, Any]] = []
    target_arrays: list[dict[str, Any]] = []
    tree_models: dict[str, dict[str, Any]] = {}
    tree_instances: list[dict[str, Any]] = []
    base_arrays: dict[str, dict[str, Any]] = {}

    for tree_array in tree_arrays:
        tree_size_variable = _detect_size_variable(clean, declarations.get(tree_array, ""), functions)
        tree_operations = _detect_operations(functions, tree_array, structure, tree_size_variable, node_variable, segment_ast)
        operations.extend(_operation for _operation in tree_operations if _operation not in operations)
        base_array = _detect_segment_base_array(functions, tree_array) if structure == "segment_tree" else None
        field_arrays = [
            *grouped_field_arrays.get(tree_array, []),
            *_detect_parallel_node_fields(functions, tree_array, tree_arrays),
            *_detect_struct_node_fields(functions, tree_array),
        ]
        field_arrays = _dedupe_fields(field_arrays)

        target_arrays.append(
            {
                "name": tree_array,
                "structure_type": structure,
                "index_base": index_base,
                "size_variable": tree_size_variable,
            }
        )
        if base_array and base_array != tree_array and base_array not in base_arrays:
            base_arrays[base_array] = {
                "name": base_array,
                "structure_type": "array",
                "index_base": index_base,
                "size_variable": tree_size_variable,
                "role": "base_array",
                "source_for": tree_array,
            }

        model = _tree_model(tree_array, structure, node_variable)
        if base_array and base_array != tree_array:
            model["base_array"] = base_array
        if field_arrays:
            model["node_fields"] = field_arrays
        tree_models[tree_array] = model
        tree_instances.append(
            {
                "tree_id": tree_array,
                "array": tree_array,
                "kind": structure,
                "base_array": base_array or "",
                "node_fields": field_arrays,
                "index_base": index_base,
            }
        )

    target_arrays.extend(base_arrays.values())
    for tree_array, model in tree_models.items():
        for field in model.get("node_fields", []):
            field_array = field.get("array")
            if not field_array or any(item["name"] == field_array for item in target_arrays):
                continue
            if "." in str(field_array):
                continue
            target_arrays.append(
                {
                    "name": field_array,
                    "structure_type": "array",
                    "index_base": index_base,
                    "size_variable": size_variable,
                    "role": field.get("role", "node_field"),
                    "source_for": tree_array,
                }
            )

    if not operations:
        operations = _detect_operations(functions, array_name, structure, size_variable, node_variable, segment_ast)

    config: dict[str, Any] = {
        "target_arrays": target_arrays,
        "operations": operations,
        "tree_model": tree_models or {array_name: _tree_model(array_name, structure, node_variable)},
        "tree_instances": tree_instances,
        "watch_expressions": _default_watch_expressions(structure, node_variable),
        "auto_watch_scalars": True,
        "limits": {"timeout_seconds": 5},
        "detected": {
            "array": array_name,
            "arrays": tree_arrays,
            "structure_type": structure,
            "size_variable": size_variable,
            "node_variable": node_variable,
            "base_array": tree_instances[0].get("base_array", "") if tree_instances else "",
            "tree_instance_count": len(tree_instances),
            "operation_count": len(operations),
            "role_inference": "ast" if segment_ast.functions else "regex_fallback",
            "role_confidence": round(segment_ast.confidence, 3),
            "role_errors": segment_ast.errors,
        },
    }
    return _merge_overrides(config, overrides)


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*", "", source)


def _array_declarations(source: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    vector_pattern = re.compile(
        r"\b(?:std::)?vector\s*<[^>;]+>\s+(?P<name>[A-Za-z_]\w*)\s*\(\s*(?P<size>[^,\)]+)",
        flags=re.MULTILINE,
    )
    for match in vector_pattern.finditer(source):
        declarations.setdefault(match.group("name"), match.group("size").strip())

    c_array_pattern = re.compile(
        r"\b(?:long\s+long|int|long|short|double|float|char|bool|[A-Za-z_]\w*)\s+(?P<decls>[^;\n]*\[[^\]]+\][^;\n]*)\s*;",
        flags=re.MULTILINE,
    )
    for match in c_array_pattern.finditer(source):
        for part in _split_params(match.group("decls")):
            array_match = re.search(r"\b(?P<name>[A-Za-z_]\w*)\s*\[\s*(?P<size>[^\]]+)\s*\]", part)
            if array_match:
                declarations.setdefault(array_match.group("name"), array_match.group("size").strip())
    return declarations


def _subscript_names(source: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\[", source):
        name = match.group(1)
        if name not in {"if", "for", "while", "switch"} and name not in names:
            names.append(name)
    return names


def _functions(source: str) -> list[FunctionDef]:
    results: list[FunctionDef] = []
    pattern = re.compile(
        r"(?m)^\s*(?:template\s*<[^>]+>\s*)?"
        r"(?!if\b|for\b|while\b|switch\b|catch\b)"
        r"[\w:<>,&*\s]+\s+"
        r"(?P<name>[A-Za-z_]\w*)\s*\((?P<params>[^;{}]*)\)\s*\{"
    )
    for match in pattern.finditer(source):
        name = match.group("name")
        if name in {"if", "for", "while", "switch", "catch"}:
            continue
        open_pos = match.end() - 1
        close_pos = _find_matching_brace(source, open_pos)
        if close_pos is None:
            continue
        results.append(FunctionDef(name=name, params=_param_names(match.group("params")), body=source[match.end():close_pos]))
    return results


def _find_matching_brace(source: str, open_pos: int) -> int | None:
    depth = 0
    for pos in range(open_pos, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return pos
    return None


def _param_names(params: str) -> list[str]:
    names: list[str] = []
    for raw in _split_params(params):
        part = raw.split("=", 1)[0].strip()
        if not part:
            continue
        part = part.replace("&", " ").replace("*", " ")
        match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*$", part)
        if match:
            names.append(match.group(1))
    return names


def _split_params(params: str) -> list[str]:
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


def _detect_structure(source: str, functions: list[FunctionDef]) -> str:
    joined = "\n".join(function.body for function in functions)
    compact = re.sub(r"\s+", "", joined)
    if re.search(r"[A-Za-z_]\w*(?:\+=|-=)\(?[A-Za-z_]\w*&-[A-Za-z_]\w*\)?", compact) or "lowbit(" in source:
        return "fenwick"
    if (
        re.search(r"\bmid\b", joined)
        and (
            re.search(r"\b[A-Za-z_]\w*\s*\*\s*2\b", joined)
            or re.search(r"\b2\s*\*\s*[A-Za-z_]\w*\b", joined)
            or "<<" in joined
        )
    ) or re.search(r"\bmerge[A-Za-z_0-9]*\b", source):
        return "segment_tree"
    return "array"


def _choose_array(source: str, declarations: dict[str, str], subscript_names: list[str], structure: str) -> str:
    candidates = list(dict.fromkeys([*declarations.keys(), *subscript_names]))
    if not candidates:
        return "arr"
    preferred = {
        "fenwick": {"bit", "ft", "fenwick", "tree"},
        "segment_tree": {"seg", "stree", "tree", "tr", "t"},
        "array": {"match", "arr", "a", "ans", "res"},
    }[structure]

    def score(name: str) -> tuple[int, int]:
        writes = len(re.findall(rf"\b{re.escape(name)}\s*\[[^\]]+\]\s*(?:=|\+=|-=|\*=|/=)", source))
        reads = len(re.findall(rf"\b{re.escape(name)}\s*\[", source))
        value = writes * 20 + reads * 3
        if name in declarations:
            value += 12
        if name.lower() in preferred:
            value += 80
        if re.search(rf"\b{re.escape(name)}\.(push_back|pop_back|back|empty)\s*\(", source):
            value -= 60
        return value, -candidates.index(name)

    return max(candidates, key=score)


def _detect_size_variable(source: str, declared_size: str, functions: list[FunctionDef]) -> str:
    for expr in [declared_size, source]:
        if re.search(r"\bn\b", expr):
            return "n"
    identifiers = [name for name in re.findall(r"[A-Za-z_]\w*", declared_size) if name not in {"MAXN", "N"}]
    if identifiers:
        return identifiers[0]
    for function in functions:
        for param in function.params:
            if param in {"n", "sz", "size", "len"}:
                return param
    return "n"


def _detect_node_variable(functions: list[FunctionDef]) -> str:
    for function in functions:
        for param in function.params:
            if re.search(rf"\b{re.escape(param)}\s*\*\s*2\b", function.body) or re.search(rf"\b2\s*\*\s*{re.escape(param)}\b", function.body):
                return param
            if re.search(rf"\b{re.escape(param)}\s*<<\s*1\b", function.body):
                return param
    for preferred in ["v", "node", "id", "p"]:
        if any(preferred in function.params for function in functions):
            return preferred
    return "v"


def _detect_segment_index_base(source: str) -> int:
    if re.search(r"\b(?:build|update|query)\s*\(\s*1\s*,\s*1\s*,\s*n\b", source):
        return 1
    if re.search(r"\b(?:build|update|query)\s*\([^;]*,\s*1\s*,\s*n\b", source):
        return 1
    return 0


def _detect_segment_tree_arrays(
    source: str,
    functions: list[FunctionDef],
    declarations: dict[str, str],
    subscript_names: list[str],
    segment_ast: SegmentAstInference,
    primary: str,
) -> list[str]:
    candidates = list(dict.fromkeys([primary, *declarations.keys(), *subscript_names]))
    base_like = _all_segment_base_arrays(functions)
    scored: list[tuple[int, int, str]] = []
    for index, name in enumerate(candidates):
        if not name:
            continue
        score = _segment_storage_score(source, functions, name)
        if not any(
            _array_access_uses_child_formula(function.body, name)
            or _array_written_by_node_param(function.body, name, function.params)
            for function in functions
        ):
            continue
        if name in base_like and score < 10:
            continue
        if name == segment_ast.target_array:
            score += 40
        if name == primary:
            score += 20
        if score >= 10:
            scored.append((score, -index, name))
    if not scored:
        return [primary]
    scored.sort(reverse=True)
    return [name for _, _, name in scored]


def _group_parallel_field_arrays(
    functions: list[FunctionDef],
    tree_arrays: list[str],
) -> tuple[list[str], dict[str, list[dict[str, str]]]]:
    if len(tree_arrays) <= 1:
        return tree_arrays, {}

    primary = tree_arrays[0]
    logical_trees: list[str] = [primary]
    grouped: dict[str, list[dict[str, str]]] = {primary: []}
    for array in tree_arrays[1:]:
        if _looks_like_parallel_field_array(array) and _shares_segment_frame(functions, primary, array):
            grouped[primary].append({"array": array, "field": array, "role": _parallel_field_role(array)})
        else:
            logical_trees.append(array)
    return logical_trees, {tree: fields for tree, fields in grouped.items() if fields}


def _looks_like_parallel_field_array(name: str) -> bool:
    lowered = name.lower()
    if any(token in lowered for token in ["lazy", "tag", "assign", "pending"]):
        return True
    if any(token in lowered for token in ["tree", "seg", "bit", "fenwick"]):
        return False
    return lowered in {
        "sum",
        "s",
        "mx",
        "max",
        "maxv",
        "mn",
        "min",
        "minv",
        "cnt",
        "count",
        "g",
        "gcd",
        "pref",
        "prefix",
        "suff",
        "suffix",
        "best",
        "val",
        "value",
        "xr",
        "xor",
    }


def _parallel_field_role(name: str) -> str:
    lowered = name.lower()
    return "lazy_field" if any(token in lowered for token in ["lazy", "tag", "assign", "pending", "add"]) else "node_field"


def _shares_segment_frame(functions: list[FunctionDef], primary: str, candidate: str) -> bool:
    for function in functions:
        body = function.body
        if re.search(rf"\b{re.escape(primary)}\s*\[", body) and re.search(rf"\b{re.escape(candidate)}\s*\[", body):
            return True
        if not _function_has_segment_shape(function):
            continue
        if re.search(rf"\b{re.escape(primary)}\s*\[", body) and re.search(rf"\b{re.escape(candidate)}\s*\[", body):
            return True
    return False


def _dedupe_fields(fields: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field in fields:
        key = (field.get("array", ""), field.get("field", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(field)
    return result


def _segment_storage_score(source: str, functions: list[FunctionDef], name: str) -> int:
    score = 0
    for function in functions:
        body = function.body
        if not re.search(rf"\b{re.escape(name)}\s*\[", body):
            continue
        if _function_has_segment_shape(function):
            score += 5
        if _array_access_uses_child_formula(body, name):
            score += 10
        if _array_written_by_node_param(body, name, function.params):
            score += 6
        if re.search(rf"\b{re.escape(name)}\s*\[[^\]]+\](?:\s*\.\s*[A-Za-z_]\w*)?\s*=", body):
            score += 3
    if name.lower() in {"seg", "tree", "st", "sumtree", "maxtree", "mintree"}:
        score += 8
    if re.search(rf"\b{re.escape(name)}\s*\[[^\]]+\](?:\s*\.\s*[A-Za-z_]\w*)?\s*=", source):
        score += 2
    return score


def _function_has_segment_shape(function: FunctionDef) -> bool:
    body = function.body
    return bool(
        re.search(r"\bmid\b", body)
        and (
            re.search(r"\b[A-Za-z_]\w*\s*\*\s*2\b", body)
            or re.search(r"\b2\s*\*\s*[A-Za-z_]\w*\b", body)
            or "<<" in body
        )
    )


def _array_access_uses_child_formula(body: str, name: str) -> bool:
    return re.search(
        rf"\b{re.escape(name)}\s*\[[^\]]*(?:\*\s*2|2\s*\*|<<\s*1)[^\]]*\]",
        body,
    ) is not None


def _array_written_by_node_param(body: str, name: str, params: list[str]) -> bool:
    for param in params:
        if not _looks_like_node_param(body, param):
            continue
        if re.search(rf"\b{re.escape(name)}\s*\[\s*{re.escape(param)}\s*\](?:\s*\.\s*[A-Za-z_]\w*)?\s*(?:=|\+=|-=|\*=|/=)", body):
            return True
    return False


def _looks_like_node_param(body: str, param: str) -> bool:
    lowered = param.lower()
    if lowered in {"v", "id", "idx", "node", "root", "p", "i"}:
        return True
    return bool(
        re.search(rf"\b{re.escape(param)}\s*\*\s*2\b", body)
        or re.search(rf"\b2\s*\*\s*{re.escape(param)}\b", body)
        or re.search(rf"\b{re.escape(param)}\s*<<\s*1\b", body)
    )


def _all_segment_base_arrays(functions: list[FunctionDef]) -> set[str]:
    bases: set[str] = set()
    for function in functions:
        for match in re.finditer(r"\b[A-Za-z_]\w*\s*\[[^\]]+\](?:\s*\.\s*[A-Za-z_]\w*)?\s*=\s*(?P<base>[A-Za-z_]\w*)\s*\[[^\]]+\]", function.body):
            bases.add(match.group("base"))
    return bases


def _detect_operations(
    functions: list[FunctionDef],
    array_name: str,
    structure: str,
    size_variable: str,
    node_variable: str,
    segment_ast: SegmentAstInference | None = None,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for function in functions:
        if function.name == "main":
            continue
        ast_roles = (segment_ast.functions.get(function.name) if segment_ast else None)
        if _is_wrapped_helper(function, functions, array_name) and not _is_ast_segment_frame(ast_roles):
            continue
        body = function.body
        name = function.name.lower()
        touches_target = re.search(rf"\b{re.escape(array_name)}\s*\[", body) is not None or array_name in function.params
        calls_target_helper = any(
            re.search(rf"\b{re.escape(other.name)}\s*\(", body) and array_name in function.params
            for other in functions
            if other.name != function.name
        )
        if not touches_target and not calls_target_helper:
            continue

        operation_type = "scan"
        params: list[str] = []
        param_roles: dict[str, str] = {}
        logical_size = size_variable
        if structure == "fenwick":
            if any(token in name for token in ["sum", "query", "get", "prefix"]):
                operation_type = "query"
            else:
                operation_type = "update"
            params = _existing_params(function.params, ["pos", "idx", "index", "i", "p"])
            if operation_type == "query" and params:
                logical_size = params[0]
        elif structure == "segment_tree":
            if ast_roles is not None and ast_roles.roles:
                operation_type = ast_roles.operation_type
                if operation_type == "query" and _function_writes_array(body, array_name) and any(
                    token in name for token in ["update", "set", "add", "assign", "apply", "push"]
                ):
                    operation_type = "update"
                if not _function_writes_array(body, array_name) and any(token in name for token in ["query", "get", "sum", "ask"]):
                    operation_type = "query"
                param_roles = {
                    role: actual
                    for role, actual in ast_roles.roles.items()
                    if actual in function.params
                }
                if operation_type == "query" and not {"ql", "qr"} <= set(param_roles):
                    legacy_params = _segment_query_params(function.params)
                    legacy_roles = _legacy_segment_roles(function.params, node_variable, operation_type, legacy_params)
                    param_roles = {**legacy_roles, **param_roles}
                params = _legacy_params_for_segment_roles(operation_type, param_roles)
            elif "build" in name:
                operation_type = "build"
                params = _existing_params(function.params, [node_variable, "v", "node", "id"])
                param_roles = _legacy_segment_roles(function.params, node_variable, operation_type, params)
            elif any(token in name for token in ["query", "get", "sum"]):
                operation_type = "query"
                params = _segment_query_params(function.params)
                param_roles = _legacy_segment_roles(function.params, node_variable, operation_type, params)
            elif any(token in name for token in ["update", "set", "add", "change"]):
                operation_type = "update"
                params = _existing_params(function.params, ["pos", "idx", "index", "p"])
                param_roles = _legacy_segment_roles(function.params, node_variable, operation_type, params)
            elif "merge" in name or _looks_like_segment_merge(body, array_name, node_variable):
                operation_type = "merge"
                params = _existing_params(function.params, [node_variable, "v", "node", "id"])
                param_roles = _legacy_segment_roles(function.params, node_variable, operation_type, params)
            else:
                operation_type = "update"
                params = _existing_params(function.params, ["pos", "idx", "index", "p"])
                param_roles = _legacy_segment_roles(function.params, node_variable, operation_type, params)
        else:
            operation_type = "scan"
            params = _existing_params(function.params, ["i", "pos", "idx", "index"])

        candidate = {
            "function_name": function.name,
            "operation_type": operation_type,
            "target_array": array_name,
            "params": params,
            "param_roles": param_roles,
            "logical_size": logical_size,
        }
        if not any(item["function_name"] == candidate["function_name"] and item["operation_type"] == candidate["operation_type"] for item in operations):
            operations.append(candidate)

    if operations:
        return operations
    fallback = "fenwick_update" if structure == "fenwick" else "segment_update" if structure == "segment_tree" else "scan"
    return [{"function_name": fallback, "operation_type": "scan", "target_array": array_name, "params": [], "logical_size": size_variable}]


def _detect_segment_base_array(functions: list[FunctionDef], target_array: str) -> str | None:
    assignment_pattern = re.compile(
        rf"\b{re.escape(target_array)}\s*\[[^\]]+\](?:\s*\.\s*[A-Za-z_]\w*)?\s*=\s*(?P<rhs>[^;]+)"
    )
    for function in functions:
        if function.name == "main":
            continue
        if "build" not in function.name.lower() and not re.search(r"\breturn\s*;", function.body):
            continue
        for match in assignment_pattern.finditer(function.body):
            rhs = match.group("rhs")
            for base_match in re.finditer(r"\b(?P<base>[A-Za-z_]\w*)\s*\[[^\]]+\]", rhs):
                base = base_match.group("base")
                if base != target_array:
                    return base
    return None


def _function_writes_array(body: str, array_name: str) -> bool:
    return re.search(
        rf"\b{re.escape(array_name)}\s*\[[^\]]+\](?:\s*\.\s*[A-Za-z_]\w*)?\s*(?:=|\+=|-=|\*=|/=)",
        body,
    ) is not None


def _detect_parallel_node_fields(functions: list[FunctionDef], tree_array: str, tree_arrays: list[str]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    known_trees = set(tree_arrays)
    candidates: dict[str, int] = {}
    for function in functions:
        if not re.search(rf"\b{re.escape(tree_array)}\s*\[", function.body):
            continue
        if not _function_has_segment_shape(function):
            continue
        for array in _subscript_names(function.body):
            if array == tree_array or array in known_trees:
                continue
            if _array_written_by_node_param(function.body, array, function.params) or _array_access_uses_child_formula(function.body, array):
                candidates[array] = candidates.get(array, 0) + 1
    for array, count in candidates.items():
        role = _parallel_field_role(array)
        if count > 0 and (role == "lazy_field" or len(candidates) == 1):
            fields.append({"array": array, "field": array, "role": role})
    return fields


def _detect_struct_node_fields(functions: list[FunctionDef], tree_array: str) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(rf"\b{re.escape(tree_array)}\s*\[[^\]]+\]\s*\.\s*(?P<field>[A-Za-z_]\w*)")
    for function in functions:
        if not _function_has_segment_shape(function):
            continue
        for match in pattern.finditer(function.body):
            field = match.group("field")
            if field in seen:
                continue
            seen.add(field)
            role = "lazy_field" if any(token in field.lower() for token in ["lazy", "tag", "assign", "add"]) else "node_field"
            fields.append({"array": f"{tree_array}.{field}", "field": field, "role": role})
    return fields


def _is_wrapped_helper(function: FunctionDef, functions: list[FunctionDef], array_name: str) -> bool:
    if not function.name.endswith("_impl"):
        return False
    public_name = function.name.removesuffix("_impl")
    for candidate in functions:
        if candidate.name != public_name:
            continue
        if array_name not in candidate.params:
            continue
        if re.search(rf"\b{re.escape(function.name)}\s*\(", candidate.body):
            return True
    return False


def _is_ast_segment_frame(ast_roles: Any) -> bool:
    if ast_roles is None:
        return False
    roles = getattr(ast_roles, "roles", {}) or {}
    return bool({"node", "lo", "hi"} <= set(roles))


def _existing_params(params: list[str], preferred: list[str]) -> list[str]:
    found: list[str] = []
    lowered = {param.lower(): param for param in params}
    for name in preferred:
        item = lowered.get(name.lower())
        if item and item not in found:
            found.append(item)
    return found


def _segment_query_params(params: list[str]) -> list[str]:
    lowered = {param.lower(): param for param in params}
    for left_name, right_name in [("ql", "qr"), ("u", "v"), ("left", "right"), ("l", "r")]:
        left = lowered.get(left_name)
        right = lowered.get(right_name)
        if left and right:
            return [left, right]
    return _existing_params(params, ["ql", "qr", "u", "v", "left", "right", "l", "r"])[:2]


def _legacy_params_for_segment_roles(operation_type: str, roles: dict[str, str]) -> list[str]:
    preferred = {
        "build": ["node"],
        "merge": ["node"],
        "update": ["pos"],
        "query": ["ql", "qr"],
    }.get(operation_type, [])
    return [roles[role] for role in preferred if role in roles]


def _legacy_segment_roles(params: list[str], node_variable: str, operation_type: str, legacy_params: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    node = _existing_params(params, [node_variable, "v", "node", "id"])
    if node:
        roles["node"] = node[0]
    lo_hi = _legacy_interval_params(params, roles.get("node"))
    if lo_hi:
        roles["lo"], roles["hi"] = lo_hi
    if operation_type == "update" and legacy_params:
        roles["pos"] = legacy_params[0]
    if operation_type == "query" and len(legacy_params) >= 2:
        roles["ql"] = legacy_params[0]
        roles["qr"] = legacy_params[1]
    return roles


def _legacy_interval_params(params: list[str], node: str | None) -> tuple[str, str] | None:
    lowered = {param.lower(): param for param in params if param != node}
    for left_name, right_name in [
        ("l", "r"),
        ("lo", "hi"),
        ("tl", "tr"),
        ("left", "right"),
        ("start", "end"),
        ("s", "e"),
    ]:
        left = lowered.get(left_name)
        right = lowered.get(right_name)
        if left and right:
            return left, right
    return None


def _looks_like_segment_merge(body: str, array_name: str, node_variable: str) -> bool:
    return re.search(
        rf"\b{re.escape(array_name)}\s*\[\s*{re.escape(node_variable)}\s*\]\s*=.*"
        rf"\b{re.escape(array_name)}\s*\[\s*{re.escape(node_variable)}\s*\*\s*2\s*\].*"
        rf"\b{re.escape(array_name)}\s*\[\s*{re.escape(node_variable)}\s*\*\s*2\s*\+\s*1\s*\]",
        body,
        flags=re.DOTALL,
    ) is not None


def _tree_model(array_name: str, structure: str, node_variable: str) -> dict[str, Any]:
    if structure == "segment_tree":
        return {
            "array": array_name,
            "kind": structure,
            "root": 1,
            "node_variable": node_variable,
            "child_expressions": [f"2*{node_variable}", f"2*{node_variable}+1"],
            "parent_expression": f"{node_variable}//2",
        }
    return {
        "array": array_name,
        "kind": structure,
        "node_variable": "i",
        "child_expressions": [],
        "parent_expression": "",
    }


def _default_watch_expressions(structure: str, node_variable: str) -> list[str]:
    if structure == "segment_tree":
        return [node_variable, "pos"]
    if structure == "fenwick":
        return ["i", "pos"]
    return ["i"]


def _merge_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overrides.items():
        if key in {"auto_detect", "detected"} or value in (None, "", [], {}):
            continue
        if key == "limits":
            result[key] = {**result.get("limits", {}), **value}
        elif key == "watch_expressions":
            watches = [str(item).strip() for item in value if str(item).strip()]
            if watches:
                result[key] = watches
        else:
            result[key] = value
    return result
