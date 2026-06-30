# Trace-Based Tree Visualizer 🌳

A full-stack web application for real-time visualization of C++ data structure traces, built with Python (REST API) and Vanilla JS/HTML/CSS.

## ✨ Features

- **Interactive Tree View:** Visualizes Fenwick and Segment Trees dynamically.
- **Source Code Mapping:** Cross-highlights tree nodes and execution traces with original C++ code.
- **Real-time Timeline:** Steps through algorithm execution step-by-step.
- **REST API Backend:** A robust Python backend orchestrating C++ compilation, tracing, and data serving.

## 🛠 Tech Stack

- **Frontend:** Vanilla JS, HTML, CSS (DOM Manipulation, Canvas/SVG drawing)
- **Backend:** Python (HTTP Server, REST API)
- **Core Engine:** C++, `libclang` for AST Parsing, JSONL

---

## Layout

- `cpp/trace.hpp`: C++17 trace writer and `TrackedArray<T>`.
- `analyzer/`: Python standard-library analyzer.
- `instrumenter/`: source-to-source instrumentation using libclang when available, with regex fallback.
- `runner/`: local C++ compile/execute wrapper.
- `web/`: standalone four-panel visualizer.
- `evaluation/`: small thesis-ready dataset and metric runner.
- `examples/`: small C++ examples.
- `tests/`: unit tests for the core recognition rules.

## Install Dependencies

```powershell
pip install -r requirements.txt
```

`libclang` is optional at runtime because the fallback instrumenter keeps the thesis pipeline runnable. It remains the intended AST engine for the final system.

## Run The Analyzer

From the repository root:

```powershell
python -m prototype.analyzer path\to\trace.jsonl --out-dir prototype_out
```

The analyzer writes:

- `prototype_out/report.json`
- `prototype_out/analysis.json`
- `prototype_out/report.html`

## Run End-To-End

Use the orchestrator through the Python API or the local server:

```powershell
python -m prototype.server --port 8080
```

Then open:

```text
http://127.0.0.1:8080
```

The API endpoint is:

```text
POST /api/analyze
```

with JSON body:

```json
{
  "source": "C++ source string",
  "config": {
    "target_arrays": [
      { "name": "bit", "structure_type": "fenwick", "index_base": 1, "size_variable": "n" }
    ],
    "operations": [
      { "function_name": "add", "operation_type": "update", "target_array": "bit", "params": ["pos"], "logical_size": "n" }
    ]
  },
  "input": ""
}
```

## Visualize

Open `prototype/web/index.html` directly and choose an `analysis.json` file, or use the server above. The visualizer provides:

- Tree View
- Source View
- Timeline View
- Findings Panel

Clicking a tree node, event, or finding cross-highlights related source lines and trace events.

## Evaluation

```powershell
python -m prototype.evaluation --output-dir prototype\build\evaluation
```

This writes:

- `prototype/build/evaluation/metrics.json`

## C++ Instrumentation Pattern

```cpp
CP_TRACE_OPEN("trace.jsonl");
cp_trace::TrackedArray<int> bit("bit", n + 1, 0, "fenwick", 1);

{
    CP_TRACE_SCOPE("fenwick_update", "bit", n);
    CP_TRACE_PARAM("pos", pos);
    for (int i = pos; i <= n; i += (i & -i)) {
        CP_TRACE_AT(bit, i) += delta;
    }
}

CP_TRACE_CLOSE();
```

The current prototype intentionally assumes that target arrays and high-level operations are marked. This matches the base-scope assumptions in Chapter 1.

The full pipeline can generate these markers automatically for the supported single-file C++17 subset.
