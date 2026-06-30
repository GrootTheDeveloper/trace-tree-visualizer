from __future__ import annotations

import argparse
from pathlib import Path

from .instrumenter import InstrumentConfig, Instrumenter


def main() -> int:
    parser = argparse.ArgumentParser(description="Instrument C++ source for trace-based analysis.")
    parser.add_argument("source")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    config = InstrumentConfig.from_json(Path(args.config))
    result = Instrumenter(config).instrument(Path(args.source), Path(args.output) if args.output else None)
    if not result.success:
        for error in result.errors:
            print(error)
        return 1
    print(f"mode={result.mode}")
    print(f"wrote {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

