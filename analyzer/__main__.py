from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import analyze_trace
from .report import write_analysis_json, write_html, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze C++ array access traces.")
    parser.add_argument("trace", help="Path to JSONL trace file.")
    parser.add_argument("--out-dir", default="prototype_out", help="Directory for report.json and report.html.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = analyze_trace(args.trace)
    write_json(result, out_dir / "report.json")
    write_analysis_json(result, out_dir / "analysis.json")
    write_html(result, out_dir / "report.html")

    print(f"operations={result.summary['operation_count']} findings={result.summary['finding_count']}")
    print(f"wrote {out_dir / 'report.json'}")
    print(f"wrote {out_dir / 'analysis.json'}")
    print(f"wrote {out_dir / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
