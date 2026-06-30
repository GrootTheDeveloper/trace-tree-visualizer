from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SegmentFunctionRoles:
    function_name: str
    operation_type: str
    target_array: str
    roles: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class SegmentAstInference:
    available: bool
    confidence: float = 0.0
    target_array: str | None = None
    index_base: int | None = None
    node_variable: str | None = None
    functions: dict[str, SegmentFunctionRoles] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class _AstFunction:
    name: str
    params: list[str]
    body: str
    cursor: Any


def infer_segment_tree_roles(source: str) -> SegmentAstInference:
    _params_for_function_name.clear()
    try:
        from clang import cindex
    except Exception as exc:
        return SegmentAstInference(available=False, errors=[f"libclang unavailable: {exc}"])

    prepared = _prepare_for_clang(source)
    try:
        translation_unit = cindex.Index.create().parse(
            "segment_probe.cpp",
            args=["-std=c++17"],
            unsaved_files=[("segment_probe.cpp", prepared)],
            options=0,
        )
    except Exception as exc:
        return SegmentAstInference(available=False, errors=[f"libclang parse failed: {exc}"])

    functions = _function_cursors(translation_unit, prepared)
    if not functions:
        return SegmentAstInference(available=True, confidence=0.0)

    target_array = _infer_target_array(functions)
    if not target_array:
        return SegmentAstInference(available=True, confidence=0.0)

    function_roles: dict[str, SegmentFunctionRoles] = {}
    node_variables: list[str] = []
    for function in functions:
        if function.name == "main":
            continue
        roles = _infer_function_roles(function, target_array)
        if roles is None:
            continue
        function_roles[function.name] = roles
        node = roles.roles.get("node")
        if node:
            node_variables.append(node)

    if not function_roles:
        return SegmentAstInference(available=True, confidence=0.0, target_array=target_array)

    index_base = _infer_index_base(functions, function_roles)
    confidence = max(role.confidence for role in function_roles.values())
    return SegmentAstInference(
        available=True,
        confidence=confidence,
        target_array=target_array,
        index_base=index_base,
        node_variable=node_variables[0] if node_variables else None,
        functions=function_roles,
    )


def _prepare_for_clang(source: str) -> str:
    source = re.sub(r"^\s*#\s*include\b.*$", "", source, flags=re.MULTILINE)
    vector_stub = (
        "namespace std { template <typename T> class vector { public: "
        "vector(); vector(int); vector(int, const T&); T &operator[](int); "
        "const T &operator[](int) const; }; }\n"
    )
    return vector_stub + source


def _function_cursors(translation_unit: Any, prepared: str) -> list[_AstFunction]:
    from clang import cindex

    results: list[_AstFunction] = []
    for cursor in translation_unit.cursor.get_children():
        if cursor.kind != cindex.CursorKind.FUNCTION_DECL:
            continue
        if cursor.spelling in {"operator[]"}:
            continue
        if not cursor.location.file or cursor.location.file.name != "segment_probe.cpp":
            continue
        params = [child.spelling for child in cursor.get_children() if child.kind == cindex.CursorKind.PARM_DECL]
        if not params and cursor.spelling != "main":
            continue
        body = _cursor_text(cursor)
        if "{" not in body:
            continue
        results.append(_AstFunction(name=cursor.spelling, params=params, body=body, cursor=cursor))
    return results


def _cursor_text(cursor: Any) -> str:
    return " ".join(token.spelling for token in cursor.get_tokens())


def _walk(cursor: Any) -> list[Any]:
    items = [cursor]
    for child in cursor.get_children():
        items.extend(_walk(child))
    return items


def _infer_target_array(functions: list[_AstFunction]) -> str | None:
    scores: dict[str, int] = {}
    for function in functions:
        for base, index_expr in _subscript_exprs(function):
            score = 1
            if any(_expr_uses_child_formula(index_expr, param) for param in function.params):
                score += 8
            if _normalize_expr(index_expr) in {_normalize_expr(param) for param in function.params}:
                score += 3
            if _has_assignment_to_base(function.body, base):
                score += 4
            scores[base] = scores.get(base, 0) + score
    if not scores:
        return None
    return max(scores, key=scores.get)


def _subscript_exprs(function: _AstFunction) -> list[tuple[str, str]]:
    from clang import cindex

    results: list[tuple[str, str]] = []
    for cursor in _walk(function.cursor):
        if cursor.kind == cindex.CursorKind.ARRAY_SUBSCRIPT_EXPR or (
            cursor.kind == cindex.CursorKind.CALL_EXPR and cursor.spelling == "operator[]"
        ):
            tokens = [token.spelling for token in cursor.get_tokens()]
            parsed = _parse_subscript_tokens(tokens)
            if parsed is not None:
                results.append(parsed)
    if results:
        return results
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\[([^\]]+)\]", function.body):
        results.append((match.group(1), match.group(2).strip()))
    return results


def _parse_subscript_tokens(tokens: list[str]) -> tuple[str, str] | None:
    if "[" not in tokens or "]" not in tokens:
        return None
    open_index = tokens.index("[")
    close_index = len(tokens) - 1 - list(reversed(tokens)).index("]")
    if open_index <= 0 or close_index <= open_index + 1:
        return None
    base = tokens[open_index - 1]
    if base == "operator[]" and open_index >= 2:
        base = tokens[open_index - 2]
    index_expr = " ".join(tokens[open_index + 1 : close_index]).strip()
    if not re.match(r"^[A-Za-z_]\w*$", base):
        return None
    return base, index_expr


def _infer_function_roles(function: _AstFunction, target_array: str) -> SegmentFunctionRoles | None:
    subscripts = [(base, expr) for base, expr in _subscript_exprs(function) if base == target_array]
    calls = _call_exprs(function)
    target_calls = [call for call in calls if call[0] == function.name or call[0] != "operator[]"]
    touches_target = bool(subscripts)
    calls_segment_helper = any(_call_has_child_formula(call, function.params) for call in target_calls)
    if not touches_target and not calls_segment_helper:
        return None

    roles: dict[str, str] = {}
    evidence: list[str] = []

    node = _infer_node_param(function, subscripts, target_calls)
    if node:
        roles["node"] = node
        evidence.append(f"node={node}")

    lo, hi, mid = _infer_interval_params(function, node)
    if lo and hi:
        roles["lo"] = lo
        roles["hi"] = hi
        evidence.append(f"interval={lo},{hi}")

    pos = _infer_update_point(function, roles, mid)
    if pos:
        roles["pos"] = pos
        evidence.append(f"pos={pos}")

    ql, qr = _infer_query_range(function, roles)
    if ql and qr:
        roles["ql"] = ql
        roles["qr"] = qr
        evidence.append(f"query_range={ql},{qr}")

    has_segment_shape = bool(
        roles.get("node")
        and (
            {"lo", "hi"} <= set(roles)
            or _has_merge_shape(function.body, target_array, roles.get("node"))
            or calls_segment_helper
        )
    )
    if not has_segment_shape:
        return None

    op_type = _infer_operation_type(function, target_array, roles, target_calls)
    if op_type is None:
        return None

    confidence = 0.4
    if node:
        confidence += 0.2
    if lo and hi:
        confidence += 0.2
    if pos or (ql and qr) or op_type in {"build", "merge"}:
        confidence += 0.2
    return SegmentFunctionRoles(
        function_name=function.name,
        operation_type=op_type,
        target_array=target_array,
        roles=roles,
        confidence=min(confidence, 1.0),
        evidence=evidence,
    )


def _infer_node_param(function: _AstFunction, subscripts: list[tuple[str, str]], calls: list[tuple[str, list[str]]]) -> str | None:
    scores: dict[str, int] = {param: 0 for param in function.params}
    for _, expr in subscripts:
        normalized = _normalize_expr(expr)
        for param in function.params:
            if normalized == _normalize_expr(param):
                scores[param] += 6
            if _expr_uses_child_formula(expr, param):
                scores[param] += 8
    for _, args in calls:
        for arg in args:
            for param in function.params:
                if _expr_uses_child_formula(arg, param):
                    scores[param] += 10
    best, score = max(scores.items(), key=lambda item: item[1])
    return best if score > 0 else None


def _infer_interval_params(function: _AstFunction, node: str | None) -> tuple[str | None, str | None, str | None]:
    mid, lo, hi = _mid_definition(function)
    if lo and hi:
        return lo, hi, mid

    equality_pair = _base_case_pair(function, excluded={item for item in [node] if item})
    if equality_pair:
        lo, hi = equality_pair
        mid = mid or _mid_name_for_pair(function, lo, hi)
        return lo, hi, mid

    params = [param for param in function.params if param != node]
    for left in params:
        for right in params:
            if left == right:
                continue
            mid_candidate = _mid_name_for_pair(function, left, right)
            if mid_candidate:
                return left, right, mid_candidate
    return None, None, mid


def _mid_definition(function: _AstFunction) -> tuple[str | None, str | None, str | None]:
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*=\s*\(?\s*([A-Za-z_]\w*)\s*\+\s*([A-Za-z_]\w*)\s*\)?\s*/\s*2", function.body):
        mid, left, right = match.groups()
        if left in function.params and right in function.params:
            return mid, left, right
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\+\s*\(\s*([A-Za-z_]\w*)\s*-\s*\2\s*\)\s*/\s*2", function.body):
        mid, left, right = match.groups()
        if left in function.params and right in function.params:
            return mid, left, right
    return None, None, None


def _mid_name_for_pair(function: _AstFunction, left: str, right: str) -> str | None:
    mid, lo, hi = _mid_definition(function)
    if {lo, hi} == {left, right}:
        return mid
    return mid


def _base_case_pair(function: _AstFunction, excluded: set[str]) -> tuple[str, str] | None:
    for left, right in re.findall(r"\b([A-Za-z_]\w*)\s*==\s*([A-Za-z_]\w*)\b", function.body):
        if left in function.params and right in function.params and left not in excluded and right not in excluded:
            return left, right
    return None


def _infer_update_point(function: _AstFunction, roles: dict[str, str], mid: str | None) -> str | None:
    if not mid:
        return None
    excluded = set(roles.values())
    for condition in _if_conditions(function):
        if not re.search(rf"\b{re.escape(mid)}\b", condition):
            continue
        for param in function.params:
            if param not in excluded and re.search(rf"\b{re.escape(param)}\b", condition):
                return param
    return None


def _infer_query_range(function: _AstFunction, roles: dict[str, str]) -> tuple[str | None, str | None]:
    lo = roles.get("lo")
    hi = roles.get("hi")
    if not lo or not hi:
        return None, None
    excluded = set(roles.values())
    candidates = [param for param in function.params if param not in excluded]
    if len(candidates) < 2:
        return None, None

    conditions = " ; ".join(_if_conditions(function))
    for left in candidates:
        for right in candidates:
            if left == right:
                continue
            if _looks_like_query_pair(conditions, lo, hi, left, right):
                return left, right
    return None, None


def _looks_like_query_pair(text: str, lo: str, hi: str, ql: str, qr: str) -> bool:
    compact = _normalize_expr(text)
    lo_n, hi_n, ql_n, qr_n = map(_normalize_expr, [lo, hi, ql, qr])
    cover = f"{ql_n}<={lo_n}" in compact and f"{hi_n}<={qr_n}" in compact
    disjoint = (f"{qr_n}<{lo_n}" in compact and f"{hi_n}<{ql_n}" in compact) or (
        f"{lo_n}>{qr_n}" in compact and f"{ql_n}>{hi_n}" in compact
    )
    return cover or disjoint


def _infer_operation_type(
    function: _AstFunction,
    target_array: str,
    roles: dict[str, str],
    calls: list[tuple[str, list[str]]],
) -> str | None:
    writes_target = _has_assignment_to_base(function.body, target_array)
    recursive_child_calls = [call for call in calls if _call_has_child_formula(call, function.params)]
    
    if writes_target and len(recursive_child_calls) >= 2 and {"node", "lo", "hi"} <= set(roles):
        return "build"
    if writes_target and _has_merge_shape(function.body, target_array, roles.get("node")):
        return "merge"
        
    lowered = function.name.lower()
    
    if not writes_target:
        if "ql" in roles and "qr" in roles:
            return "query"
        if any(token in lowered for token in ["query", "get", "sum", "calc"]):
            return "query"

    if writes_target or recursive_child_calls:
        return "update"
        
    if "ql" in roles and "qr" in roles:
        return "query"
    if "pos" in roles:
        return "update"
        
    if any(token in lowered for token in ["build", "init"]):
        return "build"
    if any(token in lowered for token in ["merge", "pull", "combine"]):
        return "merge"

    return None


def _infer_index_base(functions: list[_AstFunction], roles_by_name: dict[str, SegmentFunctionRoles]) -> int | None:
    for function in functions:
        for callee, args in _call_exprs(function):
            roles = roles_by_name.get(callee)
            if roles is None:
                continue
            lo_expr = _arg_for_role(args, roles, "lo")
            node_expr = _arg_for_role(args, roles, "node")
            if _normalize_expr(node_expr or "") != "1":
                continue
            if _normalize_expr(lo_expr or "") == "1":
                return 1
            if _normalize_expr(lo_expr or "") == "0":
                return 0
    return None


def _arg_for_role(args: list[str], roles: SegmentFunctionRoles, role: str) -> str | None:
    actual = roles.roles.get(role)
    if actual is None:
        return None
    params = _params_for_function_name.get(roles.function_name, [])
    if actual not in params:
        return None
    index = params.index(actual)
    if index >= len(args):
        return None
    return args[index]


_params_for_function_name: dict[str, list[str]] = {}


def _call_exprs(function: _AstFunction) -> list[tuple[str, list[str]]]:
    from clang import cindex

    _params_for_function_name[function.name] = function.params
    calls: list[tuple[str, list[str]]] = []
    for cursor in _walk(function.cursor):
        if cursor.kind != cindex.CursorKind.CALL_EXPR:
            continue
        if cursor.spelling == "operator[]":
            continue
        tokens = [token.spelling for token in cursor.get_tokens()]
        args = _parse_call_args(tokens)
        if args is not None:
            calls.append((cursor.spelling, args))
    return calls


def _parse_call_args(tokens: list[str]) -> list[str] | None:
    if "(" not in tokens or ")" not in tokens:
        return None
    open_index = tokens.index("(")
    close_index = len(tokens) - 1 - list(reversed(tokens)).index(")")
    if close_index <= open_index:
        return []
    return _split_expr_tokens(tokens[open_index + 1 : close_index])


def _split_expr_tokens(tokens: list[str]) -> list[str]:
    parts: list[list[str]] = [[]]
    depth = 0
    for token in tokens:
        if token in {"(", "[", "{"}:
            depth += 1
        elif token in {")",
            "]",
            "}",
        } and depth:
            depth -= 1
        if token == "," and depth == 0:
            parts.append([])
        else:
            parts[-1].append(token)
    return [" ".join(part).strip() for part in parts if part]


def _call_has_child_formula(call: tuple[str, list[str]], params: list[str]) -> bool:
    return any(_expr_uses_child_formula(arg, param) for arg in call[1] for param in params)


def _expr_uses_child_formula(expr: str, param: str) -> bool:
    normalized = _normalize_expr(expr)
    param_n = _normalize_expr(param)
    left_patterns = [f"{param_n}*2", f"2*{param_n}", f"{param_n}<<1"]
    return any(pattern in normalized for pattern in left_patterns)


def _has_assignment_to_base(body: str, base: str) -> bool:
    return re.search(rf"\b{re.escape(base)}\s*\[[^\]]+\]\s*(?:[+\-*/%&|^]?=|\+\+|--)", body) is not None


def _has_merge_shape(body: str, target_array: str, node: str | None) -> bool:
    if node is None:
        return False
    compact = _normalize_expr(body)
    target = _normalize_expr(target_array)
    node_n = _normalize_expr(node)
    return f"{target}[{node_n}]=" in compact and f"{target}[{node_n}*2]" in compact


def _if_conditions(function: _AstFunction) -> list[str]:
    conditions: list[str] = []
    for match in re.finditer(r"\bif\s*\(", function.body):
        start = match.end() - 1
        end = _find_matching_paren(function.body, start)
        if end is not None:
            conditions.append(function.body[start + 1 : end])
    return conditions


def _find_matching_paren(text: str, start: int) -> int | None:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _normalize_expr(expr: str) -> str:
    return re.sub(r"\s+", "", str(expr or "").replace("(", "").replace(")", ""))
