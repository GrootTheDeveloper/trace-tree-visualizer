from __future__ import annotations

import json
from pathlib import Path

from prototype.analyzer import analyze_trace


def _trace_path(tmp_path: Path, events: list[dict]) -> Path:
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    return path


def test_graph_contains_core_node_and_edge_types(tmp_path: Path) -> None:
    path = _trace_path(
        tmp_path,
        [
            {"event": "array", "seq": 1, "array": "bit", "size": 9, "structure": "fenwick", "index_base": 1},
            {"event": "op_begin", "seq": 2, "op_id": 1, "kind": "fenwick_update", "array": "bit", "n": 8, "file": "a.cpp", "line": 4},
            {"event": "op_param", "seq": 3, "op_id": 1, "key": "pos", "value": "3"},
            {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "bit", "index": 3, "file": "a.cpp", "line": 6},
            {"event": "access", "seq": 5, "op_id": 1, "mode": "write", "array": "bit", "index": 4, "file": "a.cpp", "line": 6},
            {"event": "access", "seq": 6, "op_id": 1, "mode": "write", "array": "bit", "index": 8, "file": "a.cpp", "line": 6},
        ],
    )
    result = analyze_trace(path)
    labels = set(result.graph["summary"]["node_labels"])
    kinds = set(result.graph["summary"]["edge_kinds"])
    assert {"operation", "event", "cell", "source_line", "range"} <= labels
    assert {"belongs_to", "accesses", "source_map", "logical_cover", "access_step"} <= kinds


def test_graph_source_map_keeps_file_and_line(tmp_path: Path) -> None:
    path = _trace_path(
        tmp_path,
        [
            {"event": "op_begin", "seq": 1, "op_id": 1, "kind": "fenwick_update", "array": "bit", "n": 8},
            {"event": "op_param", "seq": 2, "op_id": 1, "key": "pos", "value": "3"},
            {"event": "access", "seq": 3, "op_id": 1, "mode": "write", "array": "bit", "index": 3, "file": "main.cpp", "line": 12},
            {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "bit", "index": 4, "file": "main.cpp", "line": 12},
            {"event": "access", "seq": 5, "op_id": 1, "mode": "write", "array": "bit", "index": 8, "file": "main.cpp", "line": 12},
        ],
    )
    result = analyze_trace(path)
    source_nodes = [node for node in result.graph["nodes"] if node["label"] == "source_line"]
    assert source_nodes[0]["attributes"]["file"] == "main.cpp"
    assert source_nodes[0]["attributes"]["line"] == 12


def test_graph_tree_link_for_segment_tree(tmp_path: Path) -> None:
    path = _trace_path(
        tmp_path,
        [
            {"event": "op_begin", "seq": 1, "op_id": 1, "kind": "segment_update", "array": "seg", "n": 8},
            {"event": "op_param", "seq": 2, "op_id": 1, "key": "pos", "value": "3"},
            {"event": "access", "seq": 3, "op_id": 1, "mode": "write", "array": "seg", "index": 11},
            {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "seg", "index": 5},
            {"event": "access", "seq": 5, "op_id": 1, "mode": "write", "array": "seg", "index": 2},
            {"event": "access", "seq": 6, "op_id": 1, "mode": "write", "array": "seg", "index": 1},
        ],
    )
    result = analyze_trace(path)
    tree_edges = [edge for edge in result.graph["edges"] if edge["kind"] == "tree_link"]
    assert any(edge["source"] == "cell:seg:1" and edge["target"] == "cell:seg:2" for edge in tree_edges)


def test_graph_temporal_dep_connects_repeated_access_to_same_cell(tmp_path: Path) -> None:
    path = _trace_path(
        tmp_path,
        [
            {"event": "op_begin", "seq": 1, "op_id": 1, "kind": "fenwick_update", "array": "bit", "n": 8},
            {"event": "op_param", "seq": 2, "op_id": 1, "key": "pos", "value": "3"},
            {"event": "access", "seq": 3, "op_id": 1, "mode": "write", "array": "bit", "index": 4},
            {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "bit", "index": 8},
            {"event": "op_begin", "seq": 5, "op_id": 2, "kind": "fenwick_update", "array": "bit", "n": 8},
            {"event": "op_param", "seq": 6, "op_id": 2, "key": "pos", "value": "4"},
            {"event": "access", "seq": 7, "op_id": 2, "mode": "write", "array": "bit", "index": 4},
            {"event": "access", "seq": 8, "op_id": 2, "mode": "write", "array": "bit", "index": 8},
        ],
    )
    result = analyze_trace(path)
    temporal_edges = [edge for edge in result.graph["edges"] if edge["kind"] == "temporal_dep"]
    assert any(edge["source"] == "event:3" and edge["target"] == "event:7" for edge in temporal_edges)
    assert any(edge["source"] == "event:4" and edge["target"] == "event:8" for edge in temporal_edges)
    assert not any(edge["source"] == "event:3" and edge["target"] == "event:8" for edge in temporal_edges)
