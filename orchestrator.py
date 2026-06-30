from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from prototype.analyzer.pipeline import analyze_trace
from prototype.analyzer.report import write_analysis_json, write_html, write_json
from prototype.instrumenter.autodetect import detect_config
from prototype.instrumenter import InstrumentConfig, Instrumenter
from prototype.runner import CppRunner, RunConfig, RunResult


@dataclass
class PipelineResult:
    run_id: str
    status: str
    analysis: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    run: dict[str, Any] = field(default_factory=dict)
    instrumentation: dict[str, Any] = field(default_factory=dict)


class PipelineOrchestrator:
    def __init__(self, runs_root: Path = Path("prototype/build/runs")):
        self.runs_root = runs_root
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def execute(self, source: str, config: dict[str, Any], input_data: str = "", run_id: str | None = None) -> PipelineResult:
        run_id = run_id or f"run_{int(time.time() * 1000)}"
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        effective_config = self._effective_config(source, config)

        source_path = run_dir / "source.cpp"
        config_path = run_dir / "trace_config.json"
        input_path = run_dir / "input.txt"
        source_path.write_text(source, encoding="utf-8")
        config_path.write_text(json.dumps(effective_config, ensure_ascii=False, indent=2), encoding="utf-8")
        input_path.write_text(input_data, encoding="utf-8")

        instrument_config = InstrumentConfig.from_dict(effective_config)
        instrument_config.output_dir = run_dir
        instrumented_path = run_dir / "instrumented.cpp"
        instrument_result = Instrumenter(instrument_config).instrument(source_path, instrumented_path)
        if not instrument_result.success or instrument_result.output_path is None:
            return PipelineResult(
                run_id=run_id,
                status="instrument_error",
                errors=instrument_result.errors,
                instrumentation={
                    **self._jsonable(asdict(instrument_result)),
                    "effective_config": self._jsonable(effective_config),
                },
                artifacts={"source": str(source_path), "config": str(config_path)},
            )

        limits = effective_config.get("limits", {})
        run_config = RunConfig(
            timeout_seconds=int(limits.get("timeout_seconds", instrument_config.timeout_seconds)),
            max_trace_events=int(limits.get("max_trace_events", instrument_config.max_trace_events)),
            build_root=run_dir,
        )
        run_result = CppRunner(run_config).run(instrumented_path, input_path, run_id="exec")
        if run_result.status != "success" or run_result.trace_path is None:
            return PipelineResult(
                run_id=run_id,
                status=run_result.status,
                errors=[run_result.stderr] if run_result.stderr else [],
                run=self._run_dict(run_result),
                instrumentation={
                    **self._jsonable(asdict(instrument_result)),
                    "effective_config": self._jsonable(effective_config),
                },
                artifacts={
                    "source": str(source_path),
                    "instrumented": str(instrumented_path),
                    "config": str(config_path),
                },
            )

        source_mapping = self._jsonable(asdict(instrument_result).get("source_mapping", []))
        analysis_config = {**effective_config, "source_mapping": source_mapping}
        analysis_result = analyze_trace(run_result.trace_path, config=analysis_config)
        analysis_result.source_files = {
            "original": source,
            "instrumented": instrumented_path.read_text(encoding="utf-8"),
        }
        analysis_result.source_mapping = source_mapping
        write_json(analysis_result, run_dir / "report.json")
        write_analysis_json(analysis_result, run_dir / "analysis.json")
        write_html(analysis_result, run_dir / "report.html")

        return PipelineResult(
            run_id=run_id,
            status="success",
            analysis=json.loads(json.dumps(asdict(analysis_result), ensure_ascii=False)),
            run=self._run_dict(run_result),
            instrumentation={
                **self._jsonable(asdict(instrument_result)),
                "effective_config": self._jsonable(effective_config),
            },
            artifacts={
                "source": str(source_path),
                "instrumented": str(instrumented_path),
                "config": str(config_path),
                "input": str(input_path),
                "trace": str(run_result.trace_path),
                "analysis": str(run_dir / "analysis.json"),
                "report": str(run_dir / "report.html"),
            },
        )

    def _effective_config(self, source: str, config: dict[str, Any]) -> dict[str, Any]:
        needs_detection = bool(config.get("auto_detect", False)) or not config.get("target_arrays") or not config.get("operations")
        if not needs_detection:
            return config
        return detect_config(source, config)

    def _run_dict(self, run_result: RunResult) -> dict[str, Any]:
        return self._jsonable(asdict(run_result))

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        return value
