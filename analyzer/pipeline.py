from __future__ import annotations

from pathlib import Path

from .fenwick import analyze_fenwick
from .graph import ExecutionGraph
from .model import Access, AnalysisResult, Finding, LineEvent, Operation, OperationResult, Trace, Watch
from .parser import load_trace
from .segment_tree import analyze_segment_tree
from .slicing import enrich_findings_with_slices
from .timeline import build_tree_timeline


def _is_actionable_finding(finding: Finding) -> bool:
    return finding.severity in {"error", "warning"}


def _base_array_names(config: dict) -> set[str]:
    names = {
        str(item.get("name"))
        for item in config.get("target_arrays", []) or []
        if item.get("role") == "base_array" and item.get("name")
    }
    tree_models = config.get("tree_model", {})
    if isinstance(tree_models, list):
        tree_models = {item.get("array"): item for item in tree_models if item.get("array")}
    if isinstance(tree_models, dict):
        for model in tree_models.values():
            if isinstance(model, dict) and model.get("base_array"):
                names.add(str(model["base_array"]))
    return names


def analyze_trace(path: str | Path, config: dict | None = None) -> AnalysisResult:
    config = config or {}
    trace = load_trace(path)
    _apply_source_mapping(trace, config.get("source_mapping"))
    base_arrays = _base_array_names(config)
    operations: list[OperationResult] = []
    findings: list[Finding] = []

    for op in trace.operations.values():
        result = analyze_fenwick(op)
        if result is None:
            result = analyze_segment_tree(op, trace)
        if result is None:
            result = OperationResult(
                op_id=op.op_id,
                kind=op.kind,
                array=op.array,
                recognized_as="non_target_unknown",
                status="rejected",
                observed_indices=[a.index for a in op.accesses],
                findings=[
                    Finding(
                        severity="info",
                        code="NON_TARGET_UNKNOWN",
                        message="Thao tác không thuộc tập luật nhận diện của nguyên mẫu cơ sở.",
                        op_id=op.op_id,
                    )
                ],
            )
        operations.append(result)
        findings.extend(result.findings)

    unscoped_diagnostics = [access for access in trace.unscoped_accesses if access.array not in base_arrays]
    if unscoped_diagnostics:
        findings.append(
            Finding(
                severity="info",
                code="UNSCOPED_ACCESSES",
                message="Some target-array accesses were not attached to a high-level operation; kept as graph context.",
                evidence={"count": len(unscoped_diagnostics)},
            )
        )

    result = AnalysisResult(
        operations=operations,
        findings=findings,
        summary={
            "array_count": len(trace.arrays),
            "operation_count": len(operations),
            "finding_count": len(findings),
            "unscoped_access_count": len(trace.unscoped_accesses),
            "watch_count": sum(len(op.watches) for op in trace.operations.values()) + len(trace.unscoped_watches),
        },
    )
    graph = ExecutionGraph.build_from_trace(trace, result)
    enrich_findings_with_slices(trace, graph, result)
    result.graph = graph.to_dict()
    result.tree_timeline = build_tree_timeline(trace, config)
    result.summary["graph_node_count"] = result.graph["summary"]["node_count"]
    result.summary["graph_edge_count"] = result.graph["summary"]["edge_count"]
    result.summary["temporal_dep_count"] = sum(1 for edge in result.graph["edges"] if edge["kind"] == "temporal_dep")
    actionable_count = sum(1 for finding in result.findings if _is_actionable_finding(finding))
    result.summary["actionable_finding_count"] = actionable_count
    result.summary["diagnostic_finding_count"] = len(result.findings) - actionable_count
    result.summary["sliced_finding_count"] = sum(1 for finding in result.findings if finding.suspect_lines)
    result.summary["timeline_step_count"] = len(result.tree_timeline.get("steps", []))
    return result


def _apply_source_mapping(trace: Trace, source_mapping: object) -> None:
    if not isinstance(source_mapping, list) or not source_mapping:
        return
    line_by_instrumented: dict[int, int] = {}
    for item in source_mapping:
        if not isinstance(item, dict):
            continue
        try:
            instrumented_line = int(item.get("instrumented_line", 0))
            original_line = int(item.get("original_line", 0))
        except (TypeError, ValueError):
            continue
        if instrumented_line > 0 and original_line > 0:
            line_by_instrumented[instrumented_line] = original_line

    if not line_by_instrumented:
        return

    for op in trace.operations.values():
        _remap_location(op, line_by_instrumented)
        for access in op.accesses:
            _remap_location(access, line_by_instrumented)
        for watch in op.watches:
            _remap_location(watch, line_by_instrumented)
        for line_event in op.line_events:
            _remap_location(line_event, line_by_instrumented)
    for access in trace.unscoped_accesses:
        _remap_location(access, line_by_instrumented)
    for watch in trace.unscoped_watches:
        _remap_location(watch, line_by_instrumented)
    for line_event in trace.unscoped_line_events:
        _remap_location(line_event, line_by_instrumented)


def _remap_location(item: Operation | Access | Watch | LineEvent, line_by_instrumented: dict[int, int]) -> None:
    if item.line <= 0:
        return
    if item.file == "source.cpp":
        return
    item.line = line_by_instrumented.get(item.line, item.line)
    if item.file:
        item.file = "source.cpp"
