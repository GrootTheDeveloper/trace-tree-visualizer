from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArrayInfo:
    name: str
    size: int
    structure: str = ""
    index_base: int = 0


@dataclass
class Access:
    seq: int
    op_id: int
    mode: str
    array: str
    index: int
    value: str = ""
    file: str = ""
    line: int = 0


@dataclass
class Watch:
    seq: int
    op_id: int
    name: str
    value: str = ""
    file: str = ""
    line: int = 0


@dataclass
class LineEvent:
    seq: int
    op_id: int
    kind: str = "statement"
    value: str = ""
    file: str = ""
    line: int = 0


@dataclass
class Operation:
    op_id: int
    kind: str
    array: str
    n: int
    parent_op_id: int = 0
    begin_seq: int = 0
    end_seq: int = 0
    file: str = ""
    line: int = 0
    params: dict[str, str] = field(default_factory=dict)
    accesses: list[Access] = field(default_factory=list)
    watches: list[Watch] = field(default_factory=list)
    line_events: list[LineEvent] = field(default_factory=list)


@dataclass
class Trace:
    arrays: dict[str, ArrayInfo] = field(default_factory=dict)
    operations: dict[int, Operation] = field(default_factory=dict)
    unscoped_accesses: list[Access] = field(default_factory=list)
    unscoped_watches: list[Watch] = field(default_factory=list)
    unscoped_line_events: list[LineEvent] = field(default_factory=list)


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    op_id: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    suspect_lines: list[str] = field(default_factory=list)


@dataclass
class Relation:
    kind: str
    source: str
    target: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationResult:
    op_id: int
    kind: str
    array: str
    recognized_as: str
    status: str
    observed_indices: list[int] = field(default_factory=list)
    expected_indices: list[int] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


@dataclass
class GraphNode:
    id: str
    label: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    operations: list[OperationResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    graph: dict[str, Any] = field(default_factory=dict)
    tree_timeline: dict[str, Any] = field(default_factory=dict)
    source_files: dict[str, str] = field(default_factory=dict)
    source_mapping: list[dict[str, Any]] = field(default_factory=list)
