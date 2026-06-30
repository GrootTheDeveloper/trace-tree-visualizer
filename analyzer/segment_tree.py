from __future__ import annotations

from dataclasses import dataclass

from .model import Access, Finding, Operation, OperationResult, Relation, Trace
from .utils import as_int, compact_indices, is_subsequence


@dataclass(frozen=True)
class SegmentNode:
    index: int
    left: int
    right: int


def build_nodes(n: int, root: int = 1, index_base: int = 0) -> dict[int, SegmentNode]:
    nodes: dict[int, SegmentNode] = {}

    def visit(index: int, left: int, right: int) -> None:
        nodes[index] = SegmentNode(index=index, left=left, right=right)
        if left == right:
            return
        mid = (left + right) // 2
        visit(index * 2, left, mid)
        visit(index * 2 + 1, mid + 1, right)

    if n > 0:
        visit(root, index_base, index_base + n - 1)
    return nodes


def update_path(n: int, pos: int, root: int = 1, index_base: int = 0) -> list[int]:
    path: list[int] = []

    def visit(index: int, left: int, right: int) -> None:
        path.append(index)
        if left == right:
            return
        mid = (left + right) // 2
        if pos <= mid:
            visit(index * 2, left, mid)
        else:
            visit(index * 2 + 1, mid + 1, right)

    if n > 0:
        visit(root, index_base, index_base + n - 1)
    return path


def range_traverse(n: int, ql: int, qr: int, root: int = 1, index_base: int = 0) -> list[int]:
    path: list[int] = []

    def visit(index: int, left: int, right: int) -> None:
        path.append(index)
        if qr < left or right < ql:
            return
        if ql <= left and right <= qr:
            return
        mid = (left + right) // 2
        visit(index * 2, left, mid)
        visit(index * 2 + 1, mid + 1, right)

    if n > 0:
        visit(root, index_base, index_base + n - 1)
    return path


def _is_segment_kind(op: Operation) -> bool:
    kind = op.kind.lower()
    return "segment" in kind or kind.startswith("seg_")


def _tree_relations(nodes: dict[int, SegmentNode], observed: list[int]) -> list[Relation]:
    unique_observed = list(dict.fromkeys(observed))
    observed_set = set(unique_observed)
    relations: list[Relation] = []
    for index in unique_observed:
        node = nodes.get(index)
        if node is None:
            continue
        relations.append(
            Relation(
                kind="logical_cover",
                source=f"node:{index}",
                target=f"range:{node.left}-{node.right}",
                attributes={"left": node.left, "right": node.right},
            )
        )
        left_child = index * 2
        right_child = index * 2 + 1
        if left_child in observed_set:
            relations.append(Relation(kind="tree_link", source=f"node:{index}", target=f"node:{left_child}", attributes={"side": "left"}))
        if right_child in observed_set:
            relations.append(Relation(kind="tree_link", source=f"node:{index}", target=f"node:{right_child}", attributes={"side": "right"}))
    return relations


def _merge_findings(op: Operation) -> list[Finding]:
    kind = op.kind.lower()
    if "merge" not in kind:
        return []
    parent = as_int(op.params.get("node") or op.params.get("v"))
    if parent <= 0:
        return []
    read_indices = compact_indices((a for a in op.accesses if a.array == op.array), mode="read")
    expected_children = [parent * 2, parent * 2 + 1]
    if read_indices[:2] == expected_children:
        return []
    return [
        Finding(
            severity="error",
            code="SEG_TREE_MISSING_CHILD_MERGE",
            message="Merge operation did not read from both left and right children. Check your merge logic (e.g. node[id] = node[2*id] + node[2*id+1]).",
            op_id=op.op_id,
            evidence={"parent": parent, "observed_reads": read_indices, "expected_children": expected_children},
        )
    ]


def analyze_segment_tree(op: Operation, trace: Trace | None = None) -> OperationResult | None:
    if not _is_segment_kind(op):
        return None

    n = _logical_n_for_tree(op, trace)
    index_base = _index_base_for(op, trace)
    nodes = build_nodes(n, root=1, index_base=index_base)
    recursive_frame = _has_same_kind_parent(op, trace)
    effective_accesses = _effective_accesses(op, trace, aggregate=not recursive_frame)
    direct_accesses = [access for access in op.accesses if access.array == op.array]
    indices = compact_indices(a for a in effective_accesses if a.array == op.array)
    kind = op.kind.lower()
    findings = _merge_findings(op)
    expected: list[int] = []
    match_indices = indices
    status = "recognized"

    if "update" in kind:
        ql = as_int(op.params.get("ql") or op.params.get("l") or op.params.get("u"))
        qr = as_int(op.params.get("qr") or op.params.get("r") or op.params.get("v"))
        pos = as_int(op.params.get("pos") or op.params.get("index"))
        if ql is not None and qr is not None:
            expected = range_traverse(n, ql, qr, root=1, index_base=index_base)
        else:
            expected = update_path(n, pos or 0, root=1, index_base=index_base)
        if recursive_frame:
            node = as_int(op.params.get("node"), 1)
            match_indices = compact_indices(direct_accesses, mode="write")
            expected = [node] if match_indices else []
        else:
            match_indices = compact_indices((a for a in effective_accesses if a.array == op.array), mode="write")
    elif "query" in kind:
        ql = as_int(op.params.get("ql") or op.params.get("l") or op.params.get("u"))
        qr = as_int(op.params.get("qr") or op.params.get("r") or op.params.get("v"))
        if ql is not None and qr is not None:
            expected = range_traverse(n, ql, qr, root=1, index_base=index_base)
        else:
            expected = []
        if recursive_frame:
            node = as_int(op.params.get("node"), 1)
            match_indices = compact_indices(direct_accesses, mode="read")
            expected = [node] if match_indices else []
        else:
            match_indices = compact_indices((a for a in effective_accesses if a.array == op.array), mode="read")

    if expected:
        acceptable = match_indices == expected or match_indices == list(reversed(expected))
        partial = is_subsequence(expected, match_indices) or is_subsequence(list(reversed(expected)), match_indices)
        if not acceptable and not partial:
            status = "mismatch"
            findings.append(
                Finding(
                    severity="warning",
                    code="SEG_TREE_ABNORMAL_TRAVERSAL",
                    message="Segment tree traversed unexpected nodes. Check for incorrect child indexing (e.g. 2*id+2), missing base cases, or redundant lazy push-downs.",
                    op_id=op.op_id,
                    evidence={"observed": match_indices, "expected": expected, "index_base": index_base},
                )
            )
        elif not acceptable:
            status = "partial"
    elif recursive_frame:
        status = "partial"

    if any(index not in nodes for index in indices):
        status = "mismatch"
        findings.append(
            Finding(
                severity="warning",
                code="SEG_TREE_INDEX_OUT_OF_BOUNDS",
                message="Accessed a node index outside the logical bounds of the tree. Check your base case to ensure recursion stops at leaf nodes.",
                op_id=op.op_id,
                evidence={"observed": indices, "n": n, "root": 1, "index_base": index_base},
            )
        )

    return OperationResult(
        op_id=op.op_id,
        kind=op.kind,
        array=op.array,
        recognized_as="segment_tree",
        status=status,
        observed_indices=match_indices,
        expected_indices=expected,
        relations=_tree_relations(nodes, indices),
        findings=findings,
    )


def _index_base_for(op: Operation, trace: Trace | None) -> int:
    if trace is None:
        return 0
    array = trace.arrays.get(op.array)
    if array is None:
        return 0
    return array.index_base


def _logical_n_for_tree(op: Operation, trace: Trace | None) -> int:
    if op.n > 0:
        return op.n
    if trace is not None:
        candidates = [item.n for item in trace.operations.values() if item.array == op.array and item.n > 0]
        if candidates:
            return candidates[0]
        ranges = [
            int(item.params["hi"]) - int(item.params["lo"]) + 1
            for item in trace.operations.values()
            if item.array == op.array and "lo" in item.params and "hi" in item.params
        ]
        if ranges:
            return max(ranges)
    if "lo" in op.params and "hi" in op.params:
        return int(op.params["hi"]) - int(op.params["lo"]) + 1
    return 0


def _has_same_kind_parent(op: Operation, trace: Trace | None) -> bool:
    if trace is None or not op.parent_op_id:
        return False
    parent = trace.operations.get(op.parent_op_id)
    return parent is not None and parent.kind == op.kind and parent.array == op.array


def _effective_accesses(op: Operation, trace: Trace | None, aggregate: bool) -> list[Access]:
    if trace is None or not aggregate:
        return sorted([access for access in op.accesses if access.array == op.array], key=lambda item: item.seq)
    accesses: list[Access] = []
    for op_id in [op.op_id, *_descendant_op_ids(trace, op.op_id)]:
        child = trace.operations.get(op_id)
        if child is None:
            continue
        accesses.extend(access for access in child.accesses if access.array == op.array)
    return sorted(accesses, key=lambda item: item.seq)


def _descendant_op_ids(trace: Trace, op_id: int) -> list[int]:
    children_by_parent: dict[int, list[int]] = {}
    for item in trace.operations.values():
        if item.parent_op_id:
            children_by_parent.setdefault(item.parent_op_id, []).append(item.op_id)

    result: list[int] = []
    stack = list(children_by_parent.get(op_id, []))
    while stack:
        current = stack.pop(0)
        result.append(current)
        stack.extend(children_by_parent.get(current, []))
    return result
