from __future__ import annotations

from pathlib import Path

from prototype.runner import CppRunner, RunConfig


def test_runner_success_with_trace(tmp_path: Path) -> None:
    source = tmp_path / "ok.cpp"
    source.write_text(
        '#include "trace.hpp"\nint main(){ CP_TRACE_OPEN("trace.jsonl"); CP_TRACE_CLOSE(); return 0; }\n',
        encoding="utf-8",
    )
    result = CppRunner(RunConfig(build_root=tmp_path / "runs")).run(source, run_id="ok")
    assert result.status == "success"
    assert result.trace_path is not None


def test_runner_preserves_global_array_registration(tmp_path: Path) -> None:
    source = tmp_path / "global_array.cpp"
    source.write_text(
        '#include "trace.hpp"\n'
        'cp_trace::TrackedArray<int> seg("seg", 16, 0, "segment_tree", 1);\n'
        'int main(){ CP_TRACE_OPEN("trace.jsonl"); CP_TRACE_WATCH("x", 1); CP_TRACE_CLOSE(); return 0; }\n',
        encoding="utf-8",
    )
    result = CppRunner(RunConfig(build_root=tmp_path / "runs")).run(source, run_id="global_array")

    assert result.status == "success"
    assert result.trace_path is not None
    lines = result.trace_path.read_text(encoding="utf-8").splitlines()
    assert '"event":"array"' in lines[0]
    assert '"array":"seg"' in lines[0]
    assert '"index_base":1' in lines[0]


def test_runner_compile_error(tmp_path: Path) -> None:
    source = tmp_path / "bad.cpp"
    source.write_text("int main(){ syntax error }\n", encoding="utf-8")
    result = CppRunner(RunConfig(build_root=tmp_path / "runs")).run(source, run_id="compile_error")
    assert result.status == "compile_error"
    assert result.stderr


def test_runner_runtime_error(tmp_path: Path) -> None:
    source = tmp_path / "runtime.cpp"
    source.write_text("int main(){ return 3; }\n", encoding="utf-8")
    result = CppRunner(RunConfig(build_root=tmp_path / "runs")).run(source, run_id="runtime")
    assert result.status == "runtime_error"
    assert result.exit_code == 3


def test_runner_timeout(tmp_path: Path) -> None:
    source = tmp_path / "timeout.cpp"
    source.write_text("int main(){ while(true){} }\n", encoding="utf-8")
    result = CppRunner(RunConfig(build_root=tmp_path / "runs", timeout_seconds=1)).run(source, run_id="timeout")
    assert result.status == "timeout"
