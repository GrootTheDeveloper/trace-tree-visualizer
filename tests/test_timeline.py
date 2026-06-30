from __future__ import annotations

import json
from pathlib import Path

from prototype.analyzer.pipeline import analyze_trace
from prototype.evaluation.dataset import segment_config, segment_source
from prototype.instrumenter import InstrumentConfig, Instrumenter
from prototype.orchestrator import PipelineOrchestrator


def _trace(tmp_path: Path, events: list[dict]) -> Path:
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    return path


def test_segment_timeline_records_progressive_node_states(tmp_path: Path) -> None:
    config = segment_config()
    config["watch_expressions"] = ["v", "pos"]
    result = PipelineOrchestrator(tmp_path / "runs").execute(segment_source(), config, run_id="segment_timeline")

    assert result.status == "success"
    timeline = result.analysis["tree_timeline"]
    assert timeline["steps"][0]["type"] == "initial"
    assert len(timeline["steps"]) > 1
    assert any(step["node_id"] == "cell:seg:1" for step in timeline["steps"])
    assert timeline["steps"][-1]["states"]["cell:seg:1"]["value"] == "11"
    assert timeline["steps"][-1]["states"]["cell:seg:1"]["created"] is True


def test_segment_timeline_reads_do_not_commit_nodes(tmp_path: Path) -> None:
    path = _trace(
        tmp_path,
        [
            {"event": "array", "seq": 1, "array": "seg", "size": 16, "structure": "segment_tree", "index_base": 0},
            {"event": "op_begin", "seq": 2, "op_id": 1, "kind": "segment_query", "array": "seg", "n": 4},
            {"event": "access", "seq": 3, "op_id": 1, "mode": "read", "array": "seg", "index": 1, "value": "0"},
            {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "seg", "index": 5, "value": "7"},
        ],
    )
    result = analyze_trace(path, config=segment_config())
    read_step = result.tree_timeline["steps"][1]
    write_step = result.tree_timeline["steps"][2]

    root_state = read_step["states"]["cell:seg:1"]
    assert root_state["observed"] is True
    assert root_state["created"] is False
    assert root_state["read_value"] == "0"
    assert root_state["value"] == ""

    leaf_state = write_step["states"]["cell:seg:5"]
    assert leaf_state["observed"] is True
    assert leaf_state["created"] is True
    assert leaf_state["value"] == "7"


def test_segment_timeline_synthesizes_complete_small_tree_shape(tmp_path: Path) -> None:
    path = _trace(
        tmp_path,
        [
            {"event": "array", "seq": 1, "array": "seg", "size": 32, "structure": "segment_tree", "index_base": 0},
            {"event": "op_begin", "seq": 2, "op_id": 1, "kind": "segment_update", "array": "seg", "n": 8},
            {"event": "op_param", "seq": 3, "op_id": 1, "key": "node", "value": "1"},
            {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "seg", "index": 1, "value": "0"},
            {"event": "op_end", "seq": 5, "op_id": 1},
        ],
    )
    result = analyze_trace(path, config=segment_config())
    nodes = {node["id"]: node for node in result.tree_timeline["nodes"]}
    edges = {(edge["source"], edge["target"]) for edge in result.tree_timeline["edges"]}

    assert nodes["cell:seg:4"]["range"] == [0, 1]
    assert nodes["cell:seg:4"]["synthesized"] is True
    assert nodes["cell:seg:8"]["range"] == [0, 0]
    assert nodes["cell:seg:8"]["synthesized"] is True
    assert nodes["cell:seg:9"]["range"] == [1, 1]
    assert nodes["cell:seg:14"]["range"] == [6, 6]
    assert nodes["cell:seg:15"]["range"] == [7, 7]
    assert ("cell:seg:4", "cell:seg:8") in edges
    assert ("cell:seg:4", "cell:seg:9") in edges
    assert ("cell:seg:7", "cell:seg:14") in edges
    assert ("cell:seg:7", "cell:seg:15") in edges


def test_segment_parallel_lazy_field_is_grouped_into_tree_node(tmp_path: Path) -> None:
    path = _trace(
        tmp_path,
        [
            {"event": "array", "seq": 1, "array": "seg", "size": 16, "structure": "segment_tree", "index_base": 0},
            {"event": "array", "seq": 2, "array": "lazy", "size": 16, "structure": "array", "index_base": 0},
            {"event": "op_begin", "seq": 3, "op_id": 1, "kind": "segment_update", "array": "seg", "n": 4},
            {"event": "op_param", "seq": 4, "op_id": 1, "key": "node", "value": "1"},
            {"event": "access", "seq": 5, "op_id": 1, "mode": "write", "array": "lazy", "index": 1, "value": "7"},
            {"event": "op_end", "seq": 6, "op_id": 1},
        ],
    )
    result = analyze_trace(
        path,
        config={
            "target_arrays": [
                {"name": "seg", "structure_type": "segment_tree", "index_base": 0},
                {"name": "lazy", "structure_type": "array", "index_base": 0, "role": "lazy_field", "source_for": "seg"},
            ],
            "tree_model": {
                "seg": {
                    "array": "seg",
                    "kind": "segment_tree",
                    "node_variable": "v",
                    "child_expressions": ["2*v", "2*v+1"],
                    "parent_expression": "v//2",
                    "node_fields": [{"array": "lazy", "field": "lazy", "role": "lazy_field"}],
                }
            },
        },
    )
    field_step = next(step for step in result.tree_timeline["steps"] if step["type"] == "field_access")
    nodes = {node["id"]: node for node in result.tree_timeline["nodes"]}

    assert field_step["node_id"] == "cell:seg:1"
    assert field_step["phase"] == "apply_lazy"
    assert field_step["states"]["cell:seg:1"]["fields"]["lazy"] == "7"
    assert "cell:lazy:1" not in nodes


def test_custom_tree_model_uses_configured_parent_formula(tmp_path: Path) -> None:
    path = _trace(
        tmp_path,
        [
            {"event": "array", "seq": 1, "array": "tree", "size": 8, "structure": "array", "index_base": 0},
            {"event": "op_begin", "seq": 2, "op_id": 1, "kind": "array_scan", "array": "tree", "n": 8},
            {"event": "access", "seq": 3, "op_id": 1, "mode": "write", "array": "tree", "index": 0, "value": "1"},
            {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "tree", "index": 1, "value": "2"},
            {"event": "access", "seq": 5, "op_id": 1, "mode": "write", "array": "tree", "index": 3, "value": "4"},
        ],
    )
    result = analyze_trace(
        path,
        config={
            "target_arrays": [{"name": "tree", "structure_type": "array"}],
            "tree_model": {
                "tree": {
                    "kind": "custom_tree",
                    "node_variable": "x",
                    "child_expressions": ["2*x+1", "2*x+2"],
                    "parent_expression": "(x-1)//2",
                }
            },
        },
    )

    edges = {(edge["source"], edge["target"]) for edge in result.tree_timeline["edges"]}
    assert ("cell:tree:0", "cell:tree:1") in edges
    assert ("cell:tree:1", "cell:tree:3") in edges


def test_auto_watch_scalar_instrumentation_keeps_if_else_valid(tmp_path: Path) -> None:
    config = segment_config()
    config["auto_watch_scalars"] = True
    source = tmp_path / "segment.cpp"
    source.write_text(segment_source(), encoding="utf-8")

    result = Instrumenter(InstrumentConfig.from_dict(config)).instrument(source, tmp_path / "instrumented.cpp")

    assert result.success
    instrumented = (tmp_path / "instrumented.cpp").read_text(encoding="utf-8")
    assert 'else { CP_TRACE_LINE' in instrumented
    assert "update_impl" in instrumented
    assert "CP_TRACE_WATCH" in instrumented
