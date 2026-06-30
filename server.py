from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from prototype.evaluation.dataset import default_dataset
from prototype.orchestrator import PipelineOrchestrator


RUNS: dict[str, dict] = {}
ORCHESTRATOR = PipelineOrchestrator()
EXAMPLE_CASES = {case.name: case for case in default_dataset()}
EXAMPLE_ALIASES = {
    "segment_bad_merge": "segment_bad_merge_01",
    "fenwick_bad_lowbit": "fenwick_bad_lowbit_01",
}
SAMPLE_ANALYSES = {
    "segment_ok_01": Path("prototype/build/evaluation/runs/segment_ok_01/analysis.json"),
    "segment_bad_merge_01": Path("prototype/build/evaluation/runs/segment_bad_merge_01/analysis.json"),
    "segment_bad_merge": Path("prototype/build/evaluation/runs/segment_bad_merge_01/analysis.json"),
    "fenwick_ok_01": Path("prototype/build/evaluation/runs/fenwick_ok_01/analysis.json"),
    "fenwick_bad_lowbit_01": Path("prototype/build/evaluation/runs/fenwick_bad_lowbit_01/analysis.json"),
    "fenwick_bad_lowbit": Path("prototype/build/evaluation/runs/fenwick_bad_lowbit_01/analysis.json"),
    "smoke_fenwick_final": Path("prototype/build/runs/smoke_fenwick_final/analysis.json"),
}


def default_analysis_path(name: str | None = None) -> Path | None:
    if name:
        name = EXAMPLE_ALIASES.get(name, name)
        sample = SAMPLE_ANALYSES.get(name)
        if sample is not None and sample.exists():
            return sample

    preferred = [
        SAMPLE_ANALYSES["segment_ok_01"],
        SAMPLE_ANALYSES["segment_bad_merge_01"],
        SAMPLE_ANALYSES["fenwick_ok_01"],
        SAMPLE_ANALYSES["fenwick_bad_lowbit_01"],
        SAMPLE_ANALYSES["smoke_fenwick_final"],
    ]
    for path in preferred:
        if path.exists():
            return path

    build_dir = Path("prototype/build")
    if not build_dir.exists():
        return None
    matches = sorted(
        build_dir.rglob("analysis.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


class AnalysisServer(SimpleHTTPRequestHandler):
    server_version = "TraceAnalyzer/0.1"

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._send_file(Path("prototype/web/index.html"), "text/html; charset=utf-8")
            return
        if path in {"/style.css", "/app.js"}:
            local = Path("prototype/web") / path.lstrip("/")
            content_type = "text/css; charset=utf-8" if path.endswith(".css") else "application/javascript; charset=utf-8"
            self._send_file(local, content_type)
            return
        if path in {"/analysis.json", "/api/sample"}:
            sample_name = parse_qs(parsed.query).get("name", [None])[0]
            sample = default_analysis_path(sample_name)
            if sample is None:
                self._send_json({"error": "no analysis.json found"}, status=404)
                return
            self._send_file(sample, "application/json; charset=utf-8")
            return
        if path == "/api/examples":
            self._send_json({
                "examples": [
                    {"name": case.name, "label": case.label}
                    for case in EXAMPLE_CASES.values()
                ]
            })
            return
        if path == "/api/example":
            example_name = parse_qs(parsed.query).get("name", ["segment_ok_01"])[0]
            example_name = EXAMPLE_ALIASES.get(example_name, example_name)
            case = EXAMPLE_CASES.get(example_name)
            if case is None:
                self._send_json({"error": "example not found"}, status=404)
                return
            self._send_json({
                "name": case.name,
                "label": case.label,
                "source": case.source,
                "input": case.input_data,
                "config": case.config,
            })
            return
        if path.startswith("/web/"):
            local = Path("prototype") / path.lstrip("/")
            content_type = "text/plain; charset=utf-8"
            if local.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif local.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif local.suffix == ".html":
                content_type = "text/html; charset=utf-8"
            self._send_file(local, content_type)
            return
        if path.startswith("/api/analysis/"):
            run_id = path.rsplit("/", 1)[-1]
            run = RUNS.get(run_id)
            if run is None:
                self._send_json({"error": "run not found"}, status=404)
                return
            self._send_json(run.get("analysis", {}))
            return
        if path.startswith("/api/source/"):
            run_id = path.rsplit("/", 1)[-1]
            run = RUNS.get(run_id)
            if run is None:
                self._send_json({"error": "run not found"}, status=404)
                return
            self._send_json(run.get("analysis", {}).get("source_files", {}))
            return
        if path.startswith("/api/trace/"):
            run_id = path.rsplit("/", 1)[-1]
            run = RUNS.get(run_id)
            trace = run.get("artifacts", {}).get("trace") if run else None
            if trace is None or not Path(trace).exists():
                self._send_json({"error": "trace not found"}, status=404)
                return
            self._send_text(Path(trace).read_text(encoding="utf-8"), "application/jsonl; charset=utf-8")
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/analyze":
            self._send_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        result = ORCHESTRATOR.execute(
            source=str(payload.get("source", "")),
            config=dict(payload.get("config", {})),
            input_data=str(payload.get("input", "")),
            run_id=payload.get("id"),
        )
        data = {
            "run_id": result.run_id,
            "status": result.status,
            "analysis": result.analysis,
            "errors": result.errors,
            "artifacts": result.artifacts,
            "run": result.run,
            "instrumentation": result.instrumentation,
        }
        RUNS[result.run_id] = data
        self._send_json(data, status=200 if result.status == "success" else 400)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json({"error": f"file not found: {path}"}, status=404)
            return
        self._send_text(path.read_text(encoding="utf-8"), content_type)

    def _send_text(self, content: str, content_type: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict, status: int = 200) -> None:
        self._send_text(json.dumps(data, ensure_ascii=False, indent=2), "application/json; charset=utf-8", status)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local trace analysis server.")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), AnalysisServer)
    print(f"Serving on http://127.0.0.1:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())