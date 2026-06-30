from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any

from .model import Access, LineEvent, Operation, Trace, Watch
from .utils import lowbit

MAX_SYNTHESIZED_SEGMENT_LEAVES = 512


def build_tree_timeline(trace: Trace, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    models = _models_by_array(config, trace)
    events = _ordered_events(trace)
    states: dict[str, dict[str, Any]] = {}
    pending_watches: dict[int, list[Watch]] = {}
    current_node_by_op: dict[int, str] = {}
    nodes_seen: dict[str, dict[str, Any]] = {}
    edges_seen: dict[tuple[str, str], dict[str, Any]] = {}
    base_sources = _base_array_sources(config, models)
    field_sources = _field_array_sources(config, models)
    base_array_names = set(base_sources.values())
    field_array_names = set(field_sources)
    base_states: dict[str, dict[str, Any]] = {}
    steps: list[dict[str, Any]] = [
        {
            "step": 0,
            "seq": 0,
            "type": "initial",
            "node_id": None,
            "op_id": None,
            "line": 0,
            "mutation": {"message": "initial state"},
            "watches": [],
            "node_state": None,
            "states": {},
            "base_states": {},
            "active_nodes": [],
            "call_stack": [],
            "phase": "initial",
        }
    ]

    for event_type, event in events:
        if event_type == "op_begin":
            assert isinstance(event, Operation)
            node_id = _node_id_for_operation(event)
            if node_id is None:
                continue
            model = models.get(event.array, _default_model(event.array, "array"))
            node_meta = _node_meta(event.array, int(event.params.get("node", 0)), model, trace, event.op_id)
            nodes_seen[node_id] = node_meta
            _add_model_edges(node_meta, model, nodes_seen, edges_seen)
            state = states.setdefault(node_id, _empty_node_state(node_meta))
            state["observed"] = True
            state["last_event"] = event.begin_seq
            state["last_mode"] = "frame"
            current_node_by_op[event.op_id] = node_id
            attached_watches = _attach_pending_watches(state, pending_watches, event.op_id)
            steps.append(
                _step(
                    len(steps),
                    event.begin_seq,
                    "op_begin",
                    node_id,
                    event.op_id,
                    event.line,
                    _operation_mutation(event, "begin"),
                    attached_watches,
                    state,
                    states,
                    base_states,
                    trace,
                    phase=_phase_for_operation(event, "begin"),
                )
            )
        elif event_type == "op_end":
            assert isinstance(event, Operation)
            node_id = _node_id_for_operation(event)
            if node_id is None:
                continue
            state = states.get(node_id)
            attached_watches = _attach_pending_watches(state, pending_watches, event.op_id)
            steps.append(
                _step(
                    len(steps),
                    event.end_seq,
                    "op_end",
                    node_id,
                    event.op_id,
                    event.line,
                    _operation_mutation(event, "end"),
                    attached_watches,
                    state,
                    states,
                    base_states,
                    trace,
                    phase=_phase_for_operation(event, "end"),
                )
            )
        elif event_type == "access":
            assert isinstance(event, Access)
            if event.array in base_array_names:
                base_id = _base_cell_id(event.array, event.index)
                base_state = base_states.setdefault(base_id, _empty_base_state(event.array, event.index))
                base_state["observed"] = True
                if event.mode == "write":
                    base_state["created"] = True
                    base_state["value"] = event.value
                    base_state["last_write"] = event.seq
                else:
                    base_state["read_value"] = event.value
                    base_state["last_read"] = event.seq
                base_state["last_event"] = event.seq
                base_state["last_mode"] = event.mode
                frame_node_id = current_node_by_op.get(event.op_id)
                node_state = states.get(frame_node_id) if frame_node_id else None
                attached_watches = _attach_pending_watches(node_state, pending_watches, event.op_id)
                steps.append(
                    _step(
                        len(steps),
                        event.seq,
                        "base_access",
                        frame_node_id,
                        event.op_id,
                        event.line,
                        {
                            "mode": event.mode,
                            "array": event.array,
                            "index": event.index,
                            "value": event.value,
                        },
                        attached_watches,
                        node_state,
                        states,
                        base_states,
                        trace,
                        phase="base_array",
                    )
                )
                continue

            if event.array in field_array_names:
                field_info = field_sources[event.array]
                tree_array = field_info["source_tree"]
                field_name = field_info["field"]
                model = models.get(tree_array, _default_model(tree_array, "segment_tree"))
                node_id = _cell_id(tree_array, event.index)
                current_node_by_op[event.op_id] = node_id
                node_meta = _node_meta(tree_array, event.index, model, trace, event.op_id)
                node_meta["tree_id"] = model.get("tree_id", tree_array)
                nodes_seen[node_id] = node_meta
                _add_model_edges(node_meta, model, nodes_seen, edges_seen)

                state = states.setdefault(node_id, _empty_node_state(node_meta))
                state["observed"] = True
                state["last_event"] = event.seq
                state["last_mode"] = event.mode
                state.setdefault("field_modes", {})[field_name] = event.mode
                state.setdefault("field_events", {})[field_name] = event.seq
                if event.mode == "write":
                    state["created"] = True
                    state.setdefault("fields", {})[field_name] = event.value
                    state.setdefault("field_writes", {})[field_name] = event.seq
                else:
                    state.setdefault("read_fields", {})[field_name] = event.value
                    state.setdefault("field_reads", {})[field_name] = event.seq
                attached_watches = _attach_pending_watches(state, pending_watches, event.op_id)
                steps.append(
                    _step(
                        len(steps),
                        event.seq,
                        "field_access",
                        node_id,
                        event.op_id,
                        event.line,
                        {
                            "mode": event.mode,
                            "array": event.array,
                            "index": event.index,
                            "value": event.value,
                            "field": field_name,
                            "source_tree": tree_array,
                        },
                        attached_watches,
                        state,
                        states,
                        base_states,
                        trace,
                        phase=_phase_for_field_access(field_info, event, trace),
                    )
                )
                continue

            model = models.get(event.array, _default_model(event.array, "array"))
            node_id = _cell_id(event.array, event.index)
            current_node_by_op[event.op_id] = node_id
            node_meta = _node_meta(event.array, event.index, model, trace, event.op_id)
            nodes_seen[node_id] = node_meta
            _add_model_edges(node_meta, model, nodes_seen, edges_seen)

            state = states.setdefault(node_id, _empty_node_state(node_meta))
            state["observed"] = True

            # Check if event.value is a JSON representation of a struct
            struct_fields = {}
            val_str = event.value
            if isinstance(val_str, str) and val_str.startswith("{") and val_str.endswith("}"):
                try:
                    import json
                    struct_fields = json.loads(val_str)
                except Exception:
                    pass

            if event.mode == "write":
                state["created"] = True
                state["value"] = event.value
                state["last_write"] = event.seq
                if isinstance(struct_fields, dict):
                    for k, v in struct_fields.items():
                        state.setdefault("fields", {})[k] = str(v)
                        state.setdefault("field_writes", {})[k] = event.seq
            else:
                state["read_value"] = event.value
                state["last_read"] = event.seq
                if isinstance(struct_fields, dict):
                    for k, v in struct_fields.items():
                        state.setdefault("read_fields", {})[k] = str(v)
                        state.setdefault("field_reads", {})[k] = event.seq

            if isinstance(struct_fields, dict):
                for k, v in struct_fields.items():
                    state.setdefault("field_modes", {})[k] = event.mode
                    state.setdefault("field_events", {})[k] = event.seq

            state["last_event"] = event.seq
            state["last_mode"] = event.mode
            attached_watches = _attach_pending_watches(state, pending_watches, event.op_id)

            steps.append(
                _step(
                    len(steps),
                    event.seq,
                    "access",
                    node_id,
                    event.op_id,
                    event.line,
                    {
                        "mode": event.mode,
                        "array": event.array,
                        "index": event.index,
                        "value": event.value,
                    },
                    attached_watches,
                    state,
                    states,
                    base_states,
                    trace,
                    phase=_phase_for_access(event, trace),
                )
            )
        elif event_type == "line":
            assert isinstance(event, LineEvent)
            node_id = current_node_by_op.get(event.op_id)
            node_state = states.get(node_id) if node_id else None
            attached_watches = _attach_pending_watches(node_state, pending_watches, event.op_id)
            steps.append(
                _step(
                    len(steps),
                    event.seq,
                    "line",
                    node_id,
                    event.op_id,
                    event.line,
                    {
                        "kind": event.kind,
                        "value": event.value,
                        "file": event.file,
                        "line": event.line,
                    },
                    attached_watches,
                    node_state,
                    states,
                    base_states,
                    trace,
                    phase="source_line",
                )
            )
        else:
            assert isinstance(event, Watch)
            node_id = current_node_by_op.get(event.op_id)
            pending_watches.setdefault(event.op_id, []).append(event)
            if node_id and node_id in states:
                states[node_id].setdefault("fields", {})[event.name] = event.value

    _synthesize_segment_tree_shapes(trace, models, nodes_seen, edges_seen)

    return {
        "model": {"arrays": models},
        "tree_instances": _tree_instances(config, models, base_sources, field_sources),
        "base_arrays": [
            {
                "array": base_array,
                "source_tree": tree_array,
                "index_base": int(models.get(base_array, models.get(tree_array, {})).get("index_base", 0)),
            }
            for tree_array, base_array in base_sources.items()
        ],
        "nodes": sorted(nodes_seen.values(), key=lambda item: (item.get("array", ""), int(item.get("index", 0)))),
        "edges": list(edges_seen.values()),
        "steps": steps,
    }


def _models_by_array(config: dict[str, Any], trace: Trace) -> dict[str, dict[str, Any]]:
    configured = {item.get("name"): dict(item) for item in config.get("target_arrays", []) if item.get("name")}
    tree_models = config.get("tree_model", {})
    if isinstance(tree_models, list):
        tree_models = {item.get("array"): item for item in tree_models if item.get("array")}
    models: dict[str, dict[str, Any]] = {}
    for name, array in trace.arrays.items():
        array_cfg = configured.get(name, {})
        model = _default_model(name, array_cfg.get("structure_type") or array.structure or "array")
        model["index_base"] = int(array_cfg.get("index_base", array.index_base))
        custom = tree_models.get(name) if isinstance(tree_models, dict) else None
        if isinstance(custom, dict):
            model.update(custom)
        model.setdefault("array", name)
        models[name] = model
    for name, array_cfg in configured.items():
        if name not in models:
            model = _default_model(name, array_cfg.get("structure_type", "array"))
            model["index_base"] = int(array_cfg.get("index_base", model.get("index_base", 0)))
            custom = tree_models.get(name) if isinstance(tree_models, dict) else None
            if isinstance(custom, dict):
                model.update(custom)
            models[name] = model
    return models


def _base_array_sources(config: dict[str, Any], models: dict[str, dict[str, Any]]) -> dict[str, str]:
    sources: dict[str, str] = {}
    tree_models = config.get("tree_model", {})
    if isinstance(tree_models, list):
        tree_models = {item.get("array"): item for item in tree_models if item.get("array")}
    if isinstance(tree_models, dict):
        for tree_array, model in tree_models.items():
            if isinstance(model, dict) and model.get("base_array"):
                sources[str(tree_array)] = str(model["base_array"])
    for item in config.get("target_arrays", []) or []:
        if item.get("role") == "base_array" and item.get("source_for") and item.get("name"):
            sources[str(item["source_for"])] = str(item["name"])
    return {tree_array: base_array for tree_array, base_array in sources.items() if tree_array in models}


def _field_array_sources(config: dict[str, Any], models: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    fields: dict[str, dict[str, str]] = {}
    tree_models = config.get("tree_model", {})
    if isinstance(tree_models, list):
        tree_models = {item.get("array"): item for item in tree_models if item.get("array")}
    if isinstance(tree_models, dict):
        for tree_array, model in tree_models.items():
            if not isinstance(model, dict):
                continue
            for item in [*(model.get("node_fields", []) or []), *(model.get("lazy_fields", []) or [])]:
                if not isinstance(item, dict) or not item.get("array"):
                    continue
                field_array = str(item["array"])
                fields[field_array] = {
                    "source_tree": str(item.get("source_tree") or tree_array),
                    "field": str(item.get("field") or field_array),
                    "role": str(item.get("role") or "node_field"),
                }
    for item in config.get("target_arrays", []) or []:
        role = str(item.get("role") or "")
        if role not in {"node_field", "lazy_field"} or not item.get("name") or not item.get("source_for"):
            continue
        field_array = str(item["name"])
        fields.setdefault(
            field_array,
            {
                "source_tree": str(item["source_for"]),
                "field": field_array,
                "role": role,
            },
        )
    return {array: info for array, info in fields.items() if info["source_tree"] in models}


def _tree_instances(
    config: dict[str, Any],
    models: dict[str, dict[str, Any]],
    base_sources: dict[str, str],
    field_sources: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    configured = config.get("tree_instances") or []
    if isinstance(configured, list) and configured:
        return configured
    instances: list[dict[str, Any]] = []
    for array, model in models.items():
        if model.get("kind") != "segment_tree":
            continue
        fields = [
            {"array": field_array, **info}
            for field_array, info in field_sources.items()
            if info.get("source_tree") == array
        ]
        instances.append(
            {
                "tree_id": str(model.get("tree_id", array)),
                "array": array,
                "kind": "segment_tree",
                "base_array": base_sources.get(array, ""),
                "node_fields": fields,
                "index_base": int(model.get("index_base", 0)),
            }
        )
    return instances


def _default_model(array: str, structure: str) -> dict[str, Any]:
    if structure == "segment_tree":
        return {
            "array": array,
            "kind": "segment_tree",
            "root": 1,
            "index_base": 0,
            "node_variable": "v",
            "child_expressions": ["2*v", "2*v+1"],
            "parent_expression": "v//2",
        }
    if structure == "fenwick":
        return {
            "array": array,
            "kind": "fenwick",
            "index_base": 1,
            "node_variable": "i",
            "child_expressions": [],
            "parent_expression": "",
        }
    return {
        "array": array,
        "kind": "array",
        "index_base": 0,
        "node_variable": "i",
        "child_expressions": [],
        "parent_expression": "",
    }


def _ordered_events(trace: Trace) -> list[tuple[str, Access | Watch | LineEvent | Operation]]:
    events: list[tuple[str, Access | Watch | LineEvent | Operation]] = []
    for op in trace.operations.values():
        if _node_id_for_operation(op) is not None:
            events.append(("op_begin", op))
            if op.end_seq:
                events.append(("op_end", op))
        events.extend(("access", access) for access in op.accesses)
        events.extend(("watch", watch) for watch in op.watches)
        events.extend(("line", line_event) for line_event in op.line_events)
    events.extend(("access", access) for access in trace.unscoped_accesses)
    events.extend(("watch", watch) for watch in trace.unscoped_watches)
    events.extend(("line", line_event) for line_event in trace.unscoped_line_events)
    return sorted(events, key=_timeline_event_sort_key)


def _timeline_event_sort_key(item: tuple[str, Access | Watch | LineEvent | Operation]) -> tuple[int, int]:
    event_type, event = item
    if isinstance(event, Operation):
        seq = event.end_seq if event_type == "op_end" else event.begin_seq
    else:
        seq = event.seq
    order = {"op_begin": 0, "line": 1, "watch": 2, "access": 3, "op_end": 4}.get(event_type, 9)
    return seq, order


def _cell_id(array: str, index: int) -> str:
    return f"cell:{array}:{index}"


def _base_cell_id(array: str, index: int) -> str:
    return f"base:{array}:{index}"


def _node_id_for_operation(op: Operation) -> str | None:
    node = op.params.get("node")
    if node is None:
        return None
    try:
        index = int(node)
    except (TypeError, ValueError):
        return None
    if not op.array:
        return None
    return _cell_id(op.array, index)


def _empty_node_state(node_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "array": node_meta.get("array", ""),
        "index": node_meta.get("index", 0),
        "range": node_meta.get("range", [node_meta.get("index", 0), node_meta.get("index", 0)]),
        "created": False,
        "observed": False,
        "fields": {},
        "value": "",
        "read_value": "",
        "last_event": None,
        "last_mode": "",
        "last_read": None,
        "last_write": None,
    }


def _empty_base_state(array: str, index: int) -> dict[str, Any]:
    return {
        "array": array,
        "index": index,
        "created": False,
        "observed": False,
        "value": "",
        "read_value": "",
        "last_event": None,
        "last_mode": "",
        "last_read": None,
        "last_write": None,
    }


def _node_meta(array: str, index: int, model: dict[str, Any], trace: Trace, op_id: int) -> dict[str, Any]:
    range_pair = _range_for_node(index, model, trace, op_id)
    return {
        "id": _cell_id(array, index),
        "array": array,
        "index": index,
        "range": range_pair,
        "kind": model.get("kind", "array"),
        "tree_id": model.get("tree_id", array),
    }


def _range_for_node(index: int, model: dict[str, Any], trace: Trace, op_id: int) -> list[int]:
    kind = model.get("kind", "array")
    if kind == "fenwick":
        return [index - lowbit(index) + 1, index]
    if kind == "segment_tree":
        op = trace.operations.get(op_id)
        exact_range = _range_from_operation_node(op, index) if op is not None else None
        if exact_range is not None:
            return exact_range
        for candidate in trace.operations.values():
            if candidate.array == model.get("array", op.array if op is not None else ""):
                exact_range = _range_from_operation_node(candidate, index)
                if exact_range is not None:
                    return exact_range
        n = _logical_n(trace, op_id)
        if n <= 0:
            return [index, index]
        return _segment_range(index, n, int(model.get("root", 1)), int(model.get("index_base", 0)))
    return [index, index]


def _range_from_operation_node(op: Operation, index: int) -> list[int] | None:
    if str(op.params.get("node", "")) != str(index):
        return None
    if "lo" not in op.params or "hi" not in op.params:
        return None
    return [int(op.params["lo"]), int(op.params["hi"])]


def _logical_n(trace: Trace, op_id: int) -> int:
    op = trace.operations.get(op_id)
    if op and op.n > 0:
        return op.n
    if op:
        candidates = [item.n for item in trace.operations.values() if item.array == op.array and item.n > 0]
        if candidates:
            return candidates[0]
        ranges = [
            int(item.params["hi"]) - int(item.params["lo"]) + 1
            for item in trace.operations.values()
            if item.array == op.array and "lo" in item.params and "hi" in item.params
        ]
        if ranges:
            return max(ranges)
    for item in trace.operations.values():
        if item.n > 0:
            return item.n
    ranges = [
        int(item.params["hi"]) - int(item.params["lo"]) + 1
        for item in trace.operations.values()
        if "lo" in item.params and "hi" in item.params
    ]
    if ranges:
        return max(ranges)
    if op and "lo" in op.params and "hi" in op.params:
        return int(op.params["hi"]) - int(op.params["lo"]) + 1
    return 0


def _logical_n_for_array(trace: Trace, array: str) -> int:
    candidates = [op.n for op in trace.operations.values() if op.array == array and op.n > 0]
    if candidates:
        return candidates[0]
    ranges = [
        int(op.params["hi"]) - int(op.params["lo"]) + 1
        for op in trace.operations.values()
        if op.array == array and "lo" in op.params and "hi" in op.params
    ]
    return max(ranges) if ranges else 0


def _synthesize_segment_tree_shapes(
    trace: Trace,
    models: dict[str, dict[str, Any]],
    nodes_seen: dict[str, dict[str, Any]],
    edges_seen: dict[tuple[str, str], dict[str, Any]],
) -> None:
    for array, model in models.items():
        if model.get("kind") != "segment_tree":
            continue
        n = _logical_n_for_array(trace, array)
        if n <= 0 or n > MAX_SYNTHESIZED_SEGMENT_LEAVES:
            continue
        root = int(model.get("root", 1))
        index_base = int(model.get("index_base", 0))
        _synthesize_segment_node(array, root, index_base, index_base + n - 1, model, nodes_seen, edges_seen)


def _synthesize_segment_node(
    array: str,
    node: int,
    left: int,
    right: int,
    model: dict[str, Any],
    nodes_seen: dict[str, dict[str, Any]],
    edges_seen: dict[tuple[str, str], dict[str, Any]],
) -> None:
    node_id = _cell_id(array, node)
    if node_id not in nodes_seen:
        nodes_seen[node_id] = {
            "id": node_id,
            "array": array,
            "index": node,
            "range": [left, right],
            "kind": "segment_tree",
            "tree_id": model.get("tree_id", array),
            "synthesized": True,
        }
    else:
        nodes_seen[node_id].setdefault("range", [left, right])
        nodes_seen[node_id].setdefault("kind", "segment_tree")
    if left >= right:
        return

    children = _segment_child_indices(node, model)
    if len(children) < 2:
        return
    mid = (left + right) // 2
    left_child, right_child = children[0], children[1]
    _add_edge(node_id, _cell_id(array, left_child), edges_seen, "tree_link")
    _add_edge(node_id, _cell_id(array, right_child), edges_seen, "tree_link")
    _synthesize_segment_node(array, left_child, left, mid, model, nodes_seen, edges_seen)
    _synthesize_segment_node(array, right_child, mid + 1, right, model, nodes_seen, edges_seen)


def _segment_child_indices(node: int, model: dict[str, Any]) -> list[int]:
    variable = str(model.get("node_variable", "v"))
    expressions = model.get("child_expressions", []) or ["2*v", "2*v+1"]
    result: list[int] = []
    for expression in expressions:
        child = _eval_index(str(expression), variable, node)
        if child is not None and child != node:
            result.append(child)
    return result


def _segment_range(index: int, n: int, root: int = 1, index_base: int = 0) -> list[int]:
    queue = [(root, index_base, index_base + n - 1)]
    limit = max(index * 4 + 8, 64)
    while queue:
        node, left, right = queue.pop(0)
        if node == index:
            return [left, right]
        if left >= right or node > limit:
            continue
        mid = (left + right) // 2
        queue.append((node * 2, left, mid))
        queue.append((node * 2 + 1, mid + 1, right))
    return [index, index]


def _add_model_edges(
    node_meta: dict[str, Any],
    model: dict[str, Any],
    nodes_seen: dict[str, dict[str, Any]],
    edges_seen: dict[tuple[str, str], dict[str, Any]],
) -> None:
    array = str(node_meta["array"])
    index = int(node_meta["index"])
    kind = str(model.get("kind", "array"))
    if kind == "fenwick":
        _add_coverage_edges(nodes_seen, edges_seen)
        return

    parent_index = _eval_index(model.get("parent_expression", ""), model.get("node_variable", "v"), index)
    if parent_index is not None and parent_index != index:
        parent_id = _cell_id(array, parent_index)
        if parent_id in nodes_seen:
            _add_edge(parent_id, node_meta["id"], edges_seen, "tree_link")

    for expression in model.get("child_expressions", []) or []:
        child_index = _eval_index(expression, model.get("node_variable", "v"), index)
        if child_index is None:
            continue
        child_id = _cell_id(array, child_index)
        if child_id in nodes_seen:
            _add_edge(node_meta["id"], child_id, edges_seen, "tree_link")


def _add_coverage_edges(nodes_seen: dict[str, dict[str, Any]], edges_seen: dict[tuple[str, str], dict[str, Any]]) -> None:
    nodes = list(nodes_seen.values())
    for child in nodes:
        child_range = child.get("range", [child["index"], child["index"]])
        child_size = int(child_range[1]) - int(child_range[0]) + 1
        parent: dict[str, Any] | None = None
        parent_size = 10**9
        for candidate in nodes:
            if candidate["id"] == child["id"]:
                continue
            candidate_range = candidate.get("range", [candidate["index"], candidate["index"]])
            size = int(candidate_range[1]) - int(candidate_range[0]) + 1
            if (
                int(candidate_range[0]) <= int(child_range[0])
                and int(candidate_range[1]) >= int(child_range[1])
                and size > child_size
                and size < parent_size
            ):
                parent = candidate
                parent_size = size
        if parent is not None:
            _add_edge(str(parent["id"]), str(child["id"]), edges_seen, "coverage_link")


def _eval_index(expression: str, variable: str, value: int) -> int | None:
    if not expression:
        return None
    try:
        result = eval(str(expression), {"__builtins__": {}}, {str(variable): value})
    except Exception:
        return None
    try:
        return int(result)
    except (TypeError, ValueError):
        return None


def _add_edge(source: str, target: str, edges_seen: dict[tuple[str, str], dict[str, Any]], kind: str) -> None:
    key = (source, target)
    if key not in edges_seen:
        edges_seen[key] = {"source": source, "target": target, "kind": kind}


def _attach_pending_watches(state: dict[str, Any] | None, pending_watches: dict[int, list[Watch]], op_id: int) -> list[dict[str, Any]]:
    pending = pending_watches.pop(op_id, [])
    if state is not None:
        for watch in pending:
            state.setdefault("fields", {})[watch.name] = watch.value
    return [asdict(watch) for watch in pending]


def _operation_mutation(op: Operation, action: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": action,
        "kind": op.kind,
        "array": op.array,
        "params": dict(op.params),
    }
    node = op.params.get("node")
    if node is not None:
        payload["index"] = node
    if "lo" in op.params and "hi" in op.params:
        payload["range"] = [int(op.params["lo"]), int(op.params["hi"])]
    return payload


def _phase_for_operation(op: Operation, action: str) -> str:
    if action == "end":
        return "return"
    kind = op.kind.lower()
    if "merge" in kind:
        return "merge_return"
    if "update" in kind or "query" in kind or "build" in kind:
        return "descend"
    return "frame"


def _phase_for_access(access: Access, trace: Trace) -> str:
    op = trace.operations.get(access.op_id)
    kind = op.kind.lower() if op is not None else ""
    if "merge" in kind:
        return "merge_return"
    if "update" in kind and access.mode == "write":
        node = op.params.get("node") if op is not None else None
        if node is not None and str(node) == str(access.index):
            return "leaf_write"
    if "query" in kind:
        return "descend"
    return "access"


def _phase_for_field_access(field_info: dict[str, str], access: Access, trace: Trace) -> str:
    role = field_info.get("role", "")
    if role == "lazy_field":
        return "push_lazy" if access.mode == "read" else "apply_lazy"
    return _phase_for_access(access, trace)


def _phase_for_watch(watch: Watch, trace: Trace) -> str:
    op = trace.operations.get(watch.op_id)
    if op is None:
        return "watch"
    return _phase_for_operation(op, "begin")


def _call_stack(trace: Trace, op_id: int | None) -> list[dict[str, Any]]:
    if not op_id:
        return []
    stack: list[Operation] = []
    seen: set[int] = set()
    current = trace.operations.get(op_id)
    while current is not None and current.op_id not in seen:
        seen.add(current.op_id)
        stack.append(current)
        current = trace.operations.get(current.parent_op_id) if current.parent_op_id else None
    stack.reverse()
    return [_operation_frame(item) for item in stack]


def _operation_frame(op: Operation) -> dict[str, Any]:
    frame: dict[str, Any] = {
        "op_id": op.op_id,
        "parent_op_id": op.parent_op_id,
        "kind": op.kind,
        "array": op.array,
        "params": dict(op.params),
        "line": op.line,
        "begin_seq": op.begin_seq,
        "end_seq": op.end_seq,
    }
    node_id = _node_id_for_operation(op)
    if node_id is not None:
        frame["node_id"] = node_id
        frame["node"] = int(op.params["node"])
    if "lo" in op.params and "hi" in op.params:
        frame["range"] = [int(op.params["lo"]), int(op.params["hi"])]
    return frame


def _active_nodes_for_stack(call_stack: list[dict[str, Any]], fallback: str | None = None) -> list[str]:
    result: list[str] = []
    for frame in call_stack:
        node_id = frame.get("node_id")
        if isinstance(node_id, str) and node_id not in result:
            result.append(node_id)
    if fallback and fallback not in result:
        result.append(fallback)
    return result


def _step(
    step_index: int,
    seq: int,
    step_type: str,
    node_id: str | None,
    op_id: int,
    line: int,
    mutation: dict[str, Any],
    watches: list[dict[str, Any]],
    node_state: dict[str, Any] | None,
    states: dict[str, dict[str, Any]],
    base_states: dict[str, dict[str, Any]],
    trace: Trace,
    phase: str,
) -> dict[str, Any]:
    stack = _call_stack(trace, op_id)
    active_fallback = None if _is_merge_read_step(phase, mutation) else node_id
    return {
        "step": step_index,
        "seq": seq,
        "type": step_type,
        "node_id": node_id,
        "op_id": op_id,
        "line": line,
        "mutation": mutation,
        "watches": watches,
        "node_state": copy.deepcopy(node_state) if node_state is not None else None,
        "states": copy.deepcopy(states),
        "base_states": copy.deepcopy(base_states),
        "active_nodes": _active_nodes_for_stack(stack, active_fallback),
        "call_stack": stack,
        "phase": phase,
    }


def _is_merge_read_step(phase: str, mutation: dict[str, Any]) -> bool:
    return phase == "merge_return" and mutation.get("mode") == "read"
