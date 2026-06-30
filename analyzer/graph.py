from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .model import Access, AnalysisResult, GraphEdge, GraphNode, OperationResult, Relation, Trace, Watch


class ExecutionGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._edge_keys: set[tuple[str, str, str, tuple[tuple[str, str], ...]]] = set()

    @staticmethod
    def operation_id(op_id: int) -> str:
        return f"operation:{op_id}"

    @staticmethod
    def event_id(seq: int) -> str:
        return f"event:{seq}"

    @staticmethod
    def cell_id(array: str, index: int) -> str:
        return f"cell:{array}:{index}"

    @staticmethod
    def range_id(array: str, left: int, right: int) -> str:
        return f"range:{array}:{left}:{right}"

    @staticmethod
    def source_line_id(file: str, line: int) -> str:
        return f"source:{file}:{line}"

    @staticmethod
    def watch_id(seq: int) -> str:
        return f"watch:{seq}"

    def add_node(self, node_id: str, label: str, **attributes: object) -> GraphNode:
        existing = self.nodes.get(node_id)
        if existing is not None:
            existing.attributes.update({k: v for k, v in attributes.items() if v is not None})
            return existing
        node = GraphNode(id=node_id, label=label, attributes={k: v for k, v in attributes.items() if v is not None})
        self.nodes[node_id] = node
        return node

    def add_edge(self, source: str, target: str, kind: str, **attributes: object) -> None:
        normalized_attrs = tuple(sorted((str(k), str(v)) for k, v in attributes.items() if v is not None))
        key = (source, target, kind, normalized_attrs)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(GraphEdge(source=source, target=target, kind=kind, attributes=dict(attributes)))

    def get_neighbors(self, node_id: str, edge_type: str | None = None) -> list[GraphNode]:
        neighbors: list[GraphNode] = []
        for edge in self.edges:
            if edge.source != node_id:
                continue
            if edge_type is not None and edge.kind != edge_type:
                continue
            target = self.nodes.get(edge.target)
            if target is not None:
                neighbors.append(target)
        return neighbors

    def get_events_for_cell(self, cell_id: str) -> list[GraphNode]:
        return [
            self.nodes[edge.source]
            for edge in self.edges
            if edge.kind == "accesses" and edge.target == cell_id and edge.source in self.nodes
        ]

    def get_source_lines_for_finding(self, op_id: int | None) -> list[GraphNode]:
        if op_id is None:
            return []
        operation_node = self.operation_id(op_id)
        event_ids = {
            edge.source
            for edge in self.edges
            if edge.kind == "belongs_to" and edge.target == operation_node
        }
        source_ids = {
            edge.target
            for edge in self.edges
            if edge.kind == "source_map" and edge.source in event_ids
        }
        return [self.nodes[node_id] for node_id in sorted(source_ids) if node_id in self.nodes]

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": [asdict(node) for node in self.nodes.values()],
            "edges": [asdict(edge) for edge in self.edges],
            "summary": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "node_labels": sorted({node.label for node in self.nodes.values()}),
                "edge_kinds": sorted({edge.kind for edge in self.edges}),
            },
        }

    @classmethod
    def build_from_trace(cls, trace: Trace, analysis: AnalysisResult) -> "ExecutionGraph":
        graph = cls()
        operation_results = {result.op_id: result for result in analysis.operations}

        for op in trace.operations.values():
            op_node = cls.operation_id(op.op_id)
            graph.add_node(
                op_node,
                "operation",
                op_id=op.op_id,
                kind=op.kind,
                array=op.array,
                n=op.n,
                parent_op_id=op.parent_op_id,
                file=op.file,
                line=op.line,
                params=op.params,
                recognized_as=operation_results.get(op.op_id).recognized_as if op.op_id in operation_results else None,
            )
            if op.parent_op_id:
                graph.add_edge(op_node, cls.operation_id(op.parent_op_id), "nested_in")
            for access in op.accesses:
                graph._add_access(access, op_node)
            for watch in op.watches:
                graph._add_watch(watch, op_node)

        for access in trace.unscoped_accesses:
            graph._add_access(access, None)
        for watch in trace.unscoped_watches:
            graph._add_watch(watch, None)

        graph._add_temporal_dependencies(trace)

        for result in analysis.operations:
            graph._add_relations(result)

        return graph

    def _add_temporal_dependencies(self, trace: Trace) -> None:
        accesses: list[Access] = []
        for op in trace.operations.values():
            accesses.extend(op.accesses)
        accesses.extend(trace.unscoped_accesses)
        accesses.sort(key=lambda access: access.seq)

        last_by_cell: dict[tuple[str, int], Access] = {}
        for access in accesses:
            key = (access.array, access.index)
            previous = last_by_cell.get(key)
            if previous is not None:
                self.add_edge(
                    self.event_id(previous.seq),
                    self.event_id(access.seq),
                    "temporal_dep",
                    array=access.array,
                    index=access.index,
                    from_seq=previous.seq,
                    to_seq=access.seq,
                    from_mode=previous.mode,
                    to_mode=access.mode,
                    distance=access.seq - previous.seq,
                )
            last_by_cell[key] = access

    def _add_access(self, access: Access, operation_node: str | None) -> None:
        event_node = self.event_id(access.seq)
        cell_node = self.cell_id(access.array, access.index)
        self.add_node(
            event_node,
            "event",
            seq=access.seq,
            op_id=access.op_id,
            mode=access.mode,
            array=access.array,
            index=access.index,
            value=access.value,
            file=access.file,
            line=access.line,
        )
        self.add_node(cell_node, "cell", array=access.array, index=access.index, value=access.value, last_seq=access.seq, last_mode=access.mode)
        self.add_edge(event_node, cell_node, "accesses", mode=access.mode, value=access.value)
        if operation_node is not None:
            self.add_edge(event_node, operation_node, "belongs_to")
        if access.file and access.line:
            source_node = self.source_line_id(access.file, access.line)
            self.add_node(source_node, "source_line", file=access.file, line=access.line)
            self.add_edge(event_node, source_node, "source_map")

    def _add_watch(self, watch: Watch, operation_node: str | None) -> None:
        watch_node = self.watch_id(watch.seq)
        self.add_node(
            watch_node,
            "watch",
            seq=watch.seq,
            op_id=watch.op_id,
            name=watch.name,
            value=watch.value,
            file=watch.file,
            line=watch.line,
        )
        if operation_node is not None:
            self.add_edge(watch_node, operation_node, "belongs_to")
        if watch.file and watch.line:
            source_node = self.source_line_id(watch.file, watch.line)
            self.add_node(source_node, "source_line", file=watch.file, line=watch.line)
            self.add_edge(watch_node, source_node, "source_map")

    def _add_relations(self, result: OperationResult) -> None:
        for relation in result.relations:
            source = self._relation_endpoint(result.array, relation.source, relation)
            target = self._relation_endpoint(result.array, relation.target, relation)
            if source is None or target is None:
                continue
            self.add_edge(source, target, relation.kind, op_id=result.op_id, **relation.attributes)

    def _relation_endpoint(self, array: str, endpoint: str, relation: Relation) -> str | None:
        if endpoint.startswith("node:"):
            try:
                index = int(endpoint.split(":", 1)[1])
            except ValueError:
                return None
            node_id = self.cell_id(array, index)
            self.add_node(node_id, "cell", array=array, index=index)
            return node_id
        if endpoint.startswith("range:"):
            left = relation.attributes.get("left")
            right = relation.attributes.get("right")
            if left is None or right is None:
                pieces = endpoint.split(":", 1)[1].split("-", 1)
                if len(pieces) != 2:
                    return None
                left, right = int(pieces[0]), int(pieces[1])
            range_id = self.range_id(array, int(left), int(right))
            self.add_node(range_id, "range", array=array, left=int(left), right=int(right))
            return range_id
        return endpoint
