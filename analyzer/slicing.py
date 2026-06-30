from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .graph import ExecutionGraph
from .model import Access, AnalysisResult, Finding, GraphNode, Operation, Trace


@dataclass
class SliceEvent:
    event_id: str
    distance: int
    reason: str
    path: list[str] = field(default_factory=list)


def enrich_findings_with_slices(trace: Trace, graph: ExecutionGraph, analysis: AnalysisResult, max_depth: int = 8) -> None:
    """Attach a lightweight backward dynamic slice to each actionable finding."""
    incoming_temporal = _incoming_temporal_edges(graph)
    for finding in analysis.findings:
        seeds = _seed_events_for_finding(trace, finding)
        if not seeds:
            seeds = _operation_event_ids(trace, finding.op_id)
        if not seeds:
            continue

        slice_events = _backward_slice(seeds, incoming_temporal, max_depth=max_depth)
        ranked_lines = _rank_source_lines(graph, slice_events)
        if not ranked_lines:
            continue

        finding.suspect_lines = [f"{line['file']}:{line['line']}" for line in ranked_lines]
        existing_evidence = dict(finding.evidence)
        existing_evidence["slice"] = {
            "seed_events": seeds,
            "event_count": len(slice_events),
            "ranked_lines": ranked_lines,
        }
        finding.evidence = existing_evidence


def _incoming_temporal_edges(graph: ExecutionGraph) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    incoming: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for edge in graph.edges:
        if edge.kind != "temporal_dep":
            continue
        incoming.setdefault(edge.target, []).append((edge.source, edge.attributes))
    return incoming


def _seed_events_for_finding(trace: Trace, finding: Finding) -> list[str]:
    if finding.op_id is None:
        return []
    op = trace.operations.get(finding.op_id)
    if op is None:
        return []

    code = finding.code
    if code == "SEGMENT_BAD_MERGE_CHILDREN":
        return _merge_seed_events(op, finding.evidence)
    if code in {"FENWICK_BAD_INDEX_SEQUENCE", "SEGMENT_UNEXPECTED_INDEX_SEQUENCE", "SEGMENT_INDEX_OUTSIDE_SYNTHETIC_TREE"}:
        return _sequence_seed_events(op, finding.evidence)
    if code == "FENWICK_PARTIAL_TRACE":
        return _last_access_event(op)
    return []


def _operation_event_ids(trace: Trace, op_id: int | None) -> list[str]:
    if op_id is None:
        return []
    op = trace.operations.get(op_id)
    if op is None:
        return []
    return [ExecutionGraph.event_id(access.seq) for access in sorted(op.accesses, key=lambda item: item.seq)]


def _merge_seed_events(op: Operation, evidence: dict[str, Any]) -> list[str]:
    observed = [int(item) for item in evidence.get("observed_reads", []) if _is_intish(item)]
    expected = [int(item) for item in evidence.get("expected_children", []) if _is_intish(item)]
    target_indices = observed or expected
    read_events = [access for access in op.accesses if access.array == op.array and access.mode == "read"]
    if target_indices:
        selected = [access for access in read_events if access.index in target_indices]
        if selected:
            return [ExecutionGraph.event_id(access.seq) for access in selected]
    return [ExecutionGraph.event_id(access.seq) for access in read_events[-2:]]


def _sequence_seed_events(op: Operation, evidence: dict[str, Any]) -> list[str]:
    observed = [int(item) for item in evidence.get("observed", []) if _is_intish(item)]
    expected = [int(item) for item in evidence.get("expected", []) if _is_intish(item)]
    mismatch_index = _first_mismatch_index(observed, expected)
    if mismatch_index is None and observed:
        mismatch_index = observed[-1]
    if mismatch_index is None:
        return _last_access_event(op)

    matching = [access for access in op.accesses if access.array == op.array and access.index == mismatch_index]
    if matching:
        return [ExecutionGraph.event_id(matching[0].seq)]
    return _last_access_event(op)


def _last_access_event(op: Operation) -> list[str]:
    accesses = [access for access in op.accesses if access.array == op.array]
    if not accesses:
        return []
    return [ExecutionGraph.event_id(max(accesses, key=lambda item: item.seq).seq)]


def _first_mismatch_index(observed: list[int], expected: list[int]) -> int | None:
    for observed_index, expected_index in zip(observed, expected):
        if observed_index != expected_index:
            return observed_index
    if len(observed) > len(expected):
        return observed[len(expected)]
    if observed:
        return observed[-1]
    return None


def _backward_slice(
    seed_events: list[str],
    incoming_temporal: dict[str, list[tuple[str, dict[str, Any]]]],
    max_depth: int,
) -> list[SliceEvent]:
    queue: list[SliceEvent] = [
        SliceEvent(event_id=event_id, distance=0, reason="direct anomaly event", path=[event_id])
        for event_id in seed_events
    ]
    best: dict[str, SliceEvent] = {}

    while queue:
        item = queue.pop(0)
        previous = best.get(item.event_id)
        if previous is not None and previous.distance <= item.distance:
            continue
        best[item.event_id] = item
        if item.distance >= max_depth:
            continue
        for predecessor, attrs in incoming_temporal.get(item.event_id, []):
            reason = f"previous access to {attrs.get('array', '?')}[{attrs.get('index', '?')}]"
            queue.append(
                SliceEvent(
                    event_id=predecessor,
                    distance=item.distance + 1,
                    reason=reason,
                    path=[predecessor, *item.path],
                )
            )

    return sorted(best.values(), key=lambda item: (item.distance, item.event_id))


def _rank_source_lines(graph: ExecutionGraph, slice_events: list[SliceEvent]) -> list[dict[str, Any]]:
    event_by_id = {event.event_id: event for event in slice_events}
    line_scores: dict[tuple[str, int], dict[str, Any]] = {}

    for edge in graph.edges:
        if edge.kind != "source_map" or edge.source not in event_by_id:
            continue
        source_node = graph.nodes.get(edge.target)
        event_node = graph.nodes.get(edge.source)
        if source_node is None or event_node is None:
            continue
        line = _line_from_source_node(source_node)
        if line is None:
            continue

        slice_event = event_by_id[edge.source]
        score = 100.0 / (1 + slice_event.distance)
        attrs = event_node.attributes
        entry = line_scores.setdefault(
            line,
            {
                "file": line[0],
                "line": line[1],
                "score": 0.0,
                "reason": slice_event.reason,
                "events": [],
            },
        )
        entry["score"] = max(float(entry["score"]), score)
        if slice_event.distance == 0:
            entry["reason"] = "direct anomaly event"
        entry["events"].append(
            {
                "event": edge.source,
                "seq": attrs.get("seq"),
                "mode": attrs.get("mode"),
                "array": attrs.get("array"),
                "index": attrs.get("index"),
                "distance": slice_event.distance,
            }
        )

    ranked = sorted(
        line_scores.values(),
        key=lambda item: (-float(item["score"]), int(item["line"]), str(item["file"])),
    )
    for item in ranked:
        item["score"] = round(float(item["score"]), 3)
    return ranked


def _line_from_source_node(node: GraphNode) -> tuple[str, int] | None:
    file_name = str(node.attributes.get("file") or "source")
    try:
        line = int(node.attributes.get("line", 0))
    except (TypeError, ValueError):
        return None
    if line <= 0:
        return None
    return file_name, line


def _is_intish(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True
