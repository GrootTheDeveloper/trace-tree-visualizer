from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import EvaluationRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run thesis prototype evaluation.")
    parser.add_argument("--output-dir", default="prototype/build/evaluation")
    args = parser.parse_args()
    metrics = EvaluationRunner(Path(args.output_dir)).run()
    print(json.dumps(metrics["rq1"]["classification"], ensure_ascii=False, indent=2))
    print(f"wrote {Path(args.output_dir) / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

