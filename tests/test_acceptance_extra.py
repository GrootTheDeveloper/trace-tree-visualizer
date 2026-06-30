from __future__ import annotations

import json
from pathlib import Path

from prototype.analyzer import analyze_trace
from prototype.evaluation import EvaluationRunner
from prototype.evaluation.dataset import default_dataset, non_target_config, non_target_source
from prototype.orchestrator import PipelineOrchestrator


def _write_trace(tmp_path: Path, events: list[dict]) -> Path:
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    return path


def test_fenwick_query_bad_sequence(tmp_path: Path) -> None:
    result = analyze_trace(
        _write_trace(
            tmp_path,
            [
                {"event": "op_begin", "seq": 1, "op_id": 1, "kind": "fenwick_query", "array": "bit", "n": 7},
                {"event": "op_param", "seq": 2, "op_id": 1, "key": "pos", "value": "7"},
                {"event": "access", "seq": 3, "op_id": 1, "mode": "read", "array": "bit", "index": 7},
                {"event": "access", "seq": 4, "op_id": 1, "mode": "read", "array": "bit", "index": 5},
            ],
        )
    )
    assert result.operations[0].status == "mismatch"


def test_segment_index_outside_tree(tmp_path: Path) -> None:
    result = analyze_trace(
        _write_trace(
            tmp_path,
            [
                {"event": "op_begin", "seq": 1, "op_id": 1, "kind": "segment_update", "array": "seg", "n": 4},
                {"event": "op_param", "seq": 2, "op_id": 1, "key": "pos", "value": "1"},
                {"event": "access", "seq": 3, "op_id": 1, "mode": "write", "array": "seg", "index": 99},
            ],
        )
    )
    assert any(finding.code == "SEGMENT_INDEX_OUTSIDE_SYNTHETIC_TREE" for finding in result.operations[0].findings)


def test_non_target_end_to_end(tmp_path: Path) -> None:
    result = PipelineOrchestrator(tmp_path / "runs").execute(non_target_source(), non_target_config(), run_id="non_target")
    assert result.status == "success"
    assert result.analysis["operations"][0]["recognized_as"] == "non_target_unknown"


def test_evaluation_writes_metrics(tmp_path: Path) -> None:
    metrics = EvaluationRunner(tmp_path / "eval").run()
    assert (tmp_path / "eval" / "metrics.json").exists()
    assert "rq1" in metrics and "rq2" in metrics and "rq3" in metrics
    assert "sequence_similarity" in metrics["rq1"]
    assert "relation_metrics" in metrics["rq1"]
    assert "false_alarm_rate" in metrics["rq2"]
    assert "repeated_run_summary" in metrics["rq3"]


def test_default_dataset_has_minimum_size_and_real_world_style_cases() -> None:
    cases = default_dataset()
    assert len(cases) >= 30
    assert sum(1 for case in cases if case.is_real_world) >= 5


def test_localization_at_k_uses_bug_lines_not_detection_only(tmp_path: Path) -> None:
    runner = EvaluationRunner(tmp_path / "eval")
    analysis = {
        "findings": [
            {
                "code": "FENWICK_BAD_INDEX_SEQUENCE",
                "severity": "error",
                "suspect_lines": ["main.cpp:12"],
                "evidence": {"slice": {"ranked_lines": [{"file": "main.cpp", "line": 12, "score": 100.0}]}},
            }
        ]
    }
    miss = runner._localization_for_case(analysis, ["FENWICK_BAD_INDEX_SEQUENCE"], [30])
    hit = runner._localization_for_case(analysis, ["FENWICK_BAD_INDEX_SEQUENCE"], [12])
    assert miss["at_k"]["k1"] is False
    assert hit["at_k"]["k1"] is True
