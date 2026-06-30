from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from .model import AnalysisResult


def write_json(result: AnalysisResult, path: str | Path) -> None:
    path = Path(path)
    path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")


def write_analysis_json(result: AnalysisResult, path: str | Path) -> None:
    write_json(result, path)


def write_html(result: AnalysisResult, path: str | Path) -> None:
    rows: list[str] = []
    for op in result.operations:
        findings = "<br>".join(
            html.escape(f"[{finding.severity}] {finding.code}: {finding.message}")
            for finding in op.findings
        ) or "Không có"
        rows.append(
            "<tr>"
            f"<td>{op.op_id}</td>"
            f"<td>{html.escape(op.kind)}</td>"
            f"<td>{html.escape(op.array)}</td>"
            f"<td>{html.escape(op.recognized_as)}</td>"
            f"<td>{html.escape(op.status)}</td>"
            f"<td><code>{html.escape(str(op.observed_indices))}</code></td>"
            f"<td><code>{html.escape(str(op.expected_indices))}</code></td>"
            f"<td>{findings}</td>"
            "</tr>"
        )

    body = "\n".join(rows)
    document = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Trace Analysis Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2933; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccd3dd; padding: 8px; vertical-align: top; }}
    th {{ background: #eef2f7; }}
    code {{ white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>Trace Analysis Report</h1>
  <p>Operations: {result.summary.get("operation_count", 0)}.
     Findings: {result.summary.get("finding_count", 0)}.
     Graph: {result.summary.get("graph_node_count", 0)} nodes / {result.summary.get("graph_edge_count", 0)} edges.</p>
  <table>
    <thead>
      <tr>
        <th>Op ID</th>
        <th>Kind</th>
        <th>Array</th>
        <th>Recognized As</th>
        <th>Status</th>
        <th>Observed</th>
        <th>Expected</th>
        <th>Findings</th>
      </tr>
    </thead>
    <tbody>
      {body}
    </tbody>
  </table>
</body>
</html>
"""
    Path(path).write_text(document, encoding="utf-8")
