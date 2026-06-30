from __future__ import annotations

import json
import tracemalloc
from pathlib import Path
from typing import Any

from prototype.evaluation.dataset import DatasetCase, default_dataset
from prototype.evaluation.metrics import (
    bootstrap_macro_f1_ci,
    classification_metrics,
    majority_baseline,
    random_baseline,
    relation_counts,
    relation_metrics,
    sequence_similarity_metrics,
)
from prototype.orchestrator import PipelineOrchestrator

RQ2_FINDING_CODES = {
    "FENWICK_BAD_INDEX_SEQUENCE",
    "SEGMENT_BAD_MERGE_CHILDREN",
    "SEGMENT_UNEXPECTED_INDEX_SEQUENCE",
    "SEGMENT_INDEX_OUTSIDE_SYNTHETIC_TREE",
}


class EvaluationRunner:
    def __init__(self, output_dir: Path = Path("prototype/build/evaluation")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.orchestrator = PipelineOrchestrator(self.output_dir / "runs")

    def run(self, cases: list[DatasetCase] | None = None) -> dict[str, Any]:
        cases = cases or default_dataset()
        labels: list[str] = []
        predictions: list[str] = []
        analyses: list[dict] = []
        detections = 0
        mutant_count = 0
        false_alarms = 0
        clean_count = 0
        localization_hits = {1: 0, 3: 0, 5: 0}
        localized_mutants = 0
        bug_line_ranks: list[int] = []
        overhead: list[dict[str, Any]] = []
        case_results: list[dict[str, Any]] = []

        for case in cases:
            tracemalloc.start()
            result = self.orchestrator.execute(case.source, case.config, case.input_data, run_id=case.name)
            _, peak_memory = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            prediction = self._prediction(result.analysis)
            labels.append(case.label)
            predictions.append(prediction)
            if result.analysis:
                analyses.append(result.analysis)

            effective_bug_lines = self._effective_bug_lines(case, result.artifacts.get("instrumented"))
            finding_codes = self._finding_codes(result.analysis)
            if case.expected_findings:
                mutant_count += 1
                if any(code in finding_codes for code in case.expected_findings):
                    detections += 1
                localization = self._localization_for_case(result.analysis, case.expected_findings, effective_bug_lines)
                if localization["has_ground_truth"]:
                    localized_mutants += 1
                    for k in localization_hits:
                        if localization["at_k"][f"k{k}"]:
                            localization_hits[k] += 1
                    if localization["rank"] is not None:
                        bug_line_ranks.append(int(localization["rank"]))
            else:
                clean_count += 1
                if self._has_actionable_findings(result.analysis):
                    false_alarms += 1

            overhead.append(
                {
                    "case": case.name,
                    "status": result.status,
                    "compile_time_ms": result.run.get("compile_time_ms", 0),
                    "run_time_ms": result.run.get("run_time_ms", 0),
                    "peak_python_memory_bytes": peak_memory,
                    "trace_path": result.artifacts.get("trace"),
                    "trace_bytes": self._trace_size(result.artifacts.get("trace")),
                    "event_count": self._trace_event_count(result.artifacts.get("trace")),
                    "truncated": result.status == "timeout",
                    "runtime_overhead_ratio": None,
                    "memory_overhead_bytes": peak_memory,
                }
            )
            case_results.append(
                {
                    "name": case.name,
                    "status": result.status,
                    "label": case.label,
                    "prediction": prediction,
                    "source_family": case.source_family,
                    "is_real_world": case.is_real_world,
                    "finding_codes": sorted(finding_codes),
                    "bug_lines": effective_bug_lines,
                }
            )

        localization_denominator = localized_mutants or mutant_count
        metrics = {
            "rq1": {
                "classification": classification_metrics(labels, predictions),
                "macro_f1_ci": bootstrap_macro_f1_ci(labels, predictions),
                "random_baseline": random_baseline(labels),
                "majority_baseline": majority_baseline(labels),
                "relation_counts": relation_counts(analyses),
                "relation_metrics": relation_metrics(analyses),
                "sequence_similarity": sequence_similarity_metrics(analyses),
            },
            "rq2": {
                "mutant_count": mutant_count,
                "detected_mutants": detections,
                "detection_rate": detections / mutant_count if mutant_count else 0.0,
                "false_alarm_count": false_alarms,
                "clean_count": clean_count,
                "false_alarm_rate": false_alarms / clean_count if clean_count else 0.0,
                "localized_mutants": localized_mutants,
                "localization_at_k": {
                    f"k{k}": localization_hits[k] / localization_denominator if localization_denominator else 0.0
                    for k in sorted(localization_hits)
                },
                "mean_bug_line_rank": sum(bug_line_ranks) / len(bug_line_ranks) if bug_line_ranks else None,
            },
            "rq3": {
                "runs": overhead,
                "repeated_run_summary": self._summarize_overhead(overhead),
            },
            "cases": case_results,
            "dataset": {
                "case_count": len(cases),
                "real_world_case_count": sum(1 for case in cases if case.is_real_world),
                "families": sorted({case.source_family for case in cases}),
            },
        }
        (self.output_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        return metrics

    def _prediction(self, analysis: dict[str, Any]) -> str:
        recognized = {op.get("recognized_as") for op in analysis.get("operations", [])}
        if "fenwick_tree" in recognized:
            return "fenwick_tree"
        if "segment_tree" in recognized:
            return "segment_tree"
        return "non_target_unknown"

    def _finding_codes(self, analysis: dict[str, Any]) -> set[str]:
        return {str(finding.get("code")) for finding in analysis.get("findings", []) if finding.get("code")}

    def _has_actionable_findings(self, analysis: dict[str, Any]) -> bool:
        return any(finding.get("code") in RQ2_FINDING_CODES for finding in analysis.get("findings", []))

    def _effective_bug_lines(self, case: DatasetCase, instrumented_path: str | None) -> list[int]:
        lines = list(case.bug_lines)
        if case.bug_markers and instrumented_path:
            path = Path(instrumented_path)
            if path.exists():
                text = path.read_text(encoding="utf-8")
                marker_lines = [
                    line_no
                    for line_no, line in enumerate(text.splitlines(), start=1)
                    if any(marker in line for marker in case.bug_markers)
                ]
                if marker_lines:
                    lines = marker_lines
        return sorted(set(lines))

    def _localization_for_case(self, analysis: dict[str, Any], expected_findings: list[str], bug_lines: list[int]) -> dict[str, Any]:
        if not bug_lines:
            return {"has_ground_truth": False, "at_k": {"k1": False, "k3": False, "k5": False}, "rank": None}

        findings = [
            finding
            for finding in analysis.get("findings", [])
            if finding.get("code") in set(expected_findings)
        ]
        if not findings:
            findings = analysis.get("findings", [])

        ranked_lines = self._ranked_lines_from_findings(findings)
        rank = None
        for index, line in enumerate(ranked_lines, start=1):
            if line in bug_lines:
                rank = index
                break
        return {
            "has_ground_truth": True,
            "at_k": {f"k{k}": rank is not None and rank <= k for k in (1, 3, 5)},
            "rank": rank,
        }

    def _ranked_lines_from_findings(self, findings: list[dict[str, Any]]) -> list[int]:
        lines: list[int] = []
        for finding in findings:
            slice_data = (finding.get("evidence") or {}).get("slice") or {}
            for item in slice_data.get("ranked_lines", []):
                try:
                    line = int(item.get("line"))
                except (AttributeError, TypeError, ValueError):
                    continue
                if line not in lines:
                    lines.append(line)
            for suspect in finding.get("suspect_lines", []):
                try:
                    line = int(str(suspect).rsplit(":", 1)[1])
                except (IndexError, ValueError):
                    continue
                if line not in lines:
                    lines.append(line)
        return lines

    def _trace_size(self, trace_path: str | None) -> int:
        if not trace_path:
            return 0
        path = Path(trace_path)
        return path.stat().st_size if path.exists() else 0

    def _trace_event_count(self, trace_path: str | None) -> int:
        if not trace_path:
            return 0
        path = Path(trace_path)
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    def _summarize_overhead(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        if not runs:
            return {"run_count": 0}
        return {
            "run_count": len(runs),
            "mean_compile_time_ms": self._mean([run.get("compile_time_ms", 0) for run in runs]),
            "mean_run_time_ms": self._mean([run.get("run_time_ms", 0) for run in runs]),
            "mean_trace_bytes": self._mean([run.get("trace_bytes", 0) for run in runs]),
            "mean_event_count": self._mean([run.get("event_count", 0) for run in runs]),
            "max_peak_python_memory_bytes": max(int(run.get("peak_python_memory_bytes", 0)) for run in runs),
            "truncation_rate": sum(1 for run in runs if run.get("truncated")) / len(runs),
        }

    def _mean(self, values: list[Any]) -> float:
        numeric = [float(value or 0) for value in values]
        return sum(numeric) / len(numeric) if numeric else 0.0
