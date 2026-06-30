from __future__ import annotations

from .model import Finding, Operation, OperationResult, Relation
from .utils import as_int, compact_indices, is_subsequence, lowbit


def update_sequence(start: int, n: int) -> list[int]:
    result: list[int] = []
    index = start
    while index > 0 and index <= n:
        result.append(index)
        index += lowbit(index)
    return result


def prefix_query_sequence(start: int) -> list[int]:
    result: list[int] = []
    index = start
    while index > 0:
        result.append(index)
        index -= lowbit(index)
    return result


def _covers(indices: list[int]) -> list[Relation]:
    relations: list[Relation] = []
    for index in indices:
        lb = lowbit(index)
        if lb <= 0:
            continue
        relations.append(
            Relation(
                kind="logical_cover",
                source=f"node:{index}",
                target=f"range:{index - lb + 1}-{index}",
                attributes={"left": index - lb + 1, "right": index},
            )
        )
    return relations


def _step_relations(indices: list[int], direction: str) -> list[Relation]:
    relations: list[Relation] = []
    for src, dst in zip(indices, indices[1:]):
        relations.append(
            Relation(
                kind="access_step",
                source=f"node:{src}",
                target=f"node:{dst}",
                attributes={"direction": direction},
            )
        )
    return relations


def _is_fenwick_kind(op: Operation) -> bool:
    kind = op.kind.lower()
    return "fenwick" in kind or kind.startswith("bit_")


def analyze_fenwick(op: Operation) -> OperationResult | None:
    if not _is_fenwick_kind(op):
        return None

    indices = compact_indices(a for a in op.accesses if a.array == op.array)
    kind = op.kind.lower()
    findings: list[Finding] = []
    expected: list[int] = []
    status = "recognized"
    direction = "unknown"

    if "update" in kind:
        start = as_int(op.params.get("pos") or op.params.get("index") or (indices[0] if indices else 0))
        expected = update_sequence(start, op.n)
        direction = "increasing_lowbit"
    elif "query" in kind or "sum" in kind or "prefix" in kind:
        start = as_int(op.params.get("pos") or op.params.get("right") or op.params.get("r") or (indices[0] if indices else 0))
        expected = prefix_query_sequence(start)
        direction = "decreasing_lowbit"

    if expected:
        if indices != expected:
            if is_subsequence(expected, indices):
                status = "partial"
                findings.append(
                    Finding(
                        severity="warning",
                        code="FENWICK_PARTIAL_TRACE",
                        message="Chuỗi truy cập là dãy con của mẫu Fenwick kỳ vọng; vết thực thi có thể bị thiếu sự kiện.",
                        op_id=op.op_id,
                        evidence={"observed": indices, "expected": expected},
                    )
                )
            else:
                status = "mismatch"
                findings.append(
                    Finding(
                        severity="error",
                        code="FENWICK_BAD_INDEX_SEQUENCE",
                        message="Chuỗi chỉ số truy cập không khớp quy luật lowbit của cây Fenwick một chiều chuẩn.",
                        op_id=op.op_id,
                        evidence={"observed": indices, "expected": expected},
                    )
                )
    elif indices:
        status = "recognized_without_params"
        findings.append(
            Finding(
                severity="info",
                code="FENWICK_MISSING_OPERATION_PARAMS",
                message="Thiếu tham số thao tác để sinh chuỗi kỳ vọng; hệ thống chỉ ghi nhận quan hệ quan sát được.",
                op_id=op.op_id,
                evidence={"observed": indices},
            )
        )

    relations = _covers(indices)
    relations.extend(_step_relations(indices, direction))

    return OperationResult(
        op_id=op.op_id,
        kind=op.kind,
        array=op.array,
        recognized_as="fenwick_tree",
        status=status,
        observed_indices=indices,
        expected_indices=expected,
        relations=relations,
        findings=findings,
    )

