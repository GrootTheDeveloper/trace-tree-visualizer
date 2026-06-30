from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunConfig:
    compiler: str = "g++"
    std: str = "c++17"
    timeout_seconds: int = 10
    max_trace_events: int = 100_000
    optimization: str = "-O2"
    build_root: Path = Path("prototype/build/runs")


@dataclass
class RunResult:
    status: str
    stdout: str = ""
    stderr: str = ""
    trace_path: Path | None = None
    compile_time_ms: float = 0.0
    run_time_ms: float = 0.0
    exit_code: int = -1
    executable_path: Path | None = None
    work_dir: Path | None = None


class CppRunner:
    def __init__(self, config: RunConfig | None = None):
        self.config = config or RunConfig()

    def run(self, source_path: Path, input_path: Path | None = None, run_id: str | None = None) -> RunResult:
        source_path = Path(source_path)
        work_dir = self._prepare_work_dir(run_id)
        local_source = work_dir / source_path.name
        shutil.copy2(source_path, local_source)

        trace_header = Path("prototype/cpp/trace.hpp")
        if trace_header.exists():
            shutil.copy2(trace_header, work_dir / "trace.hpp")

        executable = work_dir / "program.exe"
        compile_cmd = [
            self.config.compiler,
            f"-std={self.config.std}",
            self.config.optimization,
            str(local_source.name),
            "-o",
            str(executable.name),
        ]

        compile_start = time.perf_counter()
        compile_proc = subprocess.run(
            compile_cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
        )
        compile_time_ms = (time.perf_counter() - compile_start) * 1000
        if compile_proc.returncode != 0:
            return RunResult(
                status="compile_error",
                stdout=compile_proc.stdout,
                stderr=compile_proc.stderr,
                compile_time_ms=compile_time_ms,
                exit_code=compile_proc.returncode,
                work_dir=work_dir,
            )

        stdin_data = ""
        if input_path is not None and Path(input_path).exists():
            stdin_data = Path(input_path).read_text(encoding="utf-8")

        run_start = time.perf_counter()
        try:
            run_proc = subprocess.run(
                [str(executable)],
                cwd=work_dir,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                status="timeout",
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                trace_path=work_dir / "trace.jsonl",
                compile_time_ms=compile_time_ms,
                run_time_ms=self.config.timeout_seconds * 1000,
                executable_path=executable,
                work_dir=work_dir,
            )

        run_time_ms = (time.perf_counter() - run_start) * 1000
        status = "success" if run_proc.returncode == 0 else "runtime_error"
        trace_path = work_dir / "trace.jsonl"
        if not trace_path.exists():
            candidates = sorted(work_dir.glob("*trace*.jsonl"))
            trace_path = candidates[0] if candidates else trace_path

        return RunResult(
            status=status,
            stdout=run_proc.stdout,
            stderr=run_proc.stderr,
            trace_path=trace_path if trace_path.exists() else None,
            compile_time_ms=compile_time_ms,
            run_time_ms=run_time_ms,
            exit_code=run_proc.returncode,
            executable_path=executable,
            work_dir=work_dir,
        )

    def _prepare_work_dir(self, run_id: str | None) -> Path:
        root = Path(self.config.build_root)
        root.mkdir(parents=True, exist_ok=True)
        if run_id is None:
            run_id = f"run_{int(time.time() * 1000)}"
        work_dir = root / run_id
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

