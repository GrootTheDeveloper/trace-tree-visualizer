from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import Access, ArrayInfo, LineEvent, Operation, Trace, Watch


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_trace(path: str | Path) -> Trace:
    trace = Trace()
    path = Path(path)

    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL trace at {path}:{line_no}: {exc}") from exc

            kind = event.get("event")
            if kind == "array":
                name = str(event.get("array", ""))
                trace.arrays[name] = ArrayInfo(
                    name=name,
                    size=_as_int(event.get("size")),
                    structure=str(event.get("structure", "")),
                    index_base=_as_int(event.get("index_base")),
                )
            elif kind == "op_begin":
                op_id = _as_int(event.get("op_id"))
                trace.operations[op_id] = Operation(
                    op_id=op_id,
                    kind=str(event.get("kind", "")),
                    array=str(event.get("array", "")),
                    n=_as_int(event.get("n")),
                    parent_op_id=_as_int(event.get("parent_op_id")),
                    begin_seq=_as_int(event.get("seq")),
                    file=str(event.get("file", "")),
                    line=_as_int(event.get("line")),
                )
            elif kind == "op_param":
                op_id = _as_int(event.get("op_id"))
                op = trace.operations.get(op_id)
                if op is not None:
                    op.params[str(event.get("key", ""))] = str(event.get("value", ""))
            elif kind == "access":
                access = Access(
                    seq=_as_int(event.get("seq")),
                    op_id=_as_int(event.get("op_id")),
                    mode=str(event.get("mode", "")),
                    array=str(event.get("array", "")),
                    index=_as_int(event.get("index")),
                    value=str(event.get("value", "")),
                    file=str(event.get("file", "")),
                    line=_as_int(event.get("line")),
                )
                op = trace.operations.get(access.op_id)
                if op is None:
                    trace.unscoped_accesses.append(access)
                else:
                    op.accesses.append(access)
            elif kind == "watch":
                watch = Watch(
                    seq=_as_int(event.get("seq")),
                    op_id=_as_int(event.get("op_id")),
                    name=str(event.get("name", "")),
                    value=str(event.get("value", "")),
                    file=str(event.get("file", "")),
                    line=_as_int(event.get("line")),
                )
                op = trace.operations.get(watch.op_id)
                if op is None:
                    trace.unscoped_watches.append(watch)
                else:
                    op.watches.append(watch)
            elif kind == "line":
                line_event = LineEvent(
                    seq=_as_int(event.get("seq")),
                    op_id=_as_int(event.get("op_id")),
                    kind=str(event.get("kind", "statement")),
                    value=str(event.get("value", "")),
                    file=str(event.get("file", "")),
                    line=_as_int(event.get("line")),
                )
                op = trace.operations.get(line_event.op_id)
                if op is None:
                    trace.unscoped_line_events.append(line_event)
                else:
                    op.line_events.append(line_event)
            elif kind == "op_end":
                op_id = _as_int(event.get("op_id"))
                op = trace.operations.get(op_id)
                if op is not None:
                    op.end_seq = _as_int(event.get("seq"))

    return trace
