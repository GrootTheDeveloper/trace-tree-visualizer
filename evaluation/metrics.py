from __future__ import annotations

from collections import Counter, defaultdict
import random
from typing import Iterable


def classification_metrics(labels: list[str], predictions: list[str]) -> dict[str, object]:
    classes = sorted(set(labels) | set(predictions))
    matrix = {label: {pred: 0 for pred in classes} for label in classes}
    for label, pred in zip(labels, predictions):
        matrix[label][pred] += 1

    per_class: dict[str, dict[str, float]] = {}
    for cls in classes:
        tp = matrix[cls][cls]
        fp = sum(matrix[label][cls] for label in classes if label != cls)
        fn = sum(matrix[cls][pred] for pred in classes if pred != cls)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[cls] = {"precision": precision, "recall": recall, "f1": f1}

    macro_f1 = sum(item["f1"] for item in per_class.values()) / len(per_class) if per_class else 0.0
    accuracy = sum(1 for label, pred in zip(labels, predictions) if label == pred) / len(labels) if labels else 0.0
    return {"classes": classes, "confusion_matrix": matrix, "per_class": per_class, "macro_f1": macro_f1, "accuracy": accuracy}


def bootstrap_macro_f1_ci(
    labels: list[str],
    predictions: list[str],
    iterations: int = 200,
    confidence: float = 0.95,
    seed: int = 13,
) -> dict[str, float | int]:
    if not labels:
        return {"lower": 0.0, "upper": 0.0, "iterations": iterations}

    rng = random.Random(seed)
    scores: list[float] = []
    indices = list(range(len(labels)))
    for _ in range(iterations):
        sample = [rng.choice(indices) for _ in indices]
        sample_labels = [labels[index] for index in sample]
        sample_predictions = [predictions[index] for index in sample]
        scores.append(float(classification_metrics(sample_labels, sample_predictions)["macro_f1"]))

    scores.sort()
    alpha = (1.0 - confidence) / 2.0
    lower_index = min(len(scores) - 1, max(0, int(alpha * len(scores))))
    upper_index = min(len(scores) - 1, max(0, int((1.0 - alpha) * len(scores)) - 1))
    return {"lower": scores[lower_index], "upper": scores[upper_index], "iterations": iterations}


def majority_baseline(labels: list[str]) -> dict[str, object]:
    if not labels:
        return classification_metrics([], [])
    majority = Counter(labels).most_common(1)[0][0]
    return classification_metrics(labels, [majority for _ in labels])


def random_baseline(labels: list[str]) -> dict[str, object]:
    if not labels:
        return classification_metrics([], [])
    classes = sorted(set(labels))
    predictions = [classes[index % len(classes)] for index, _ in enumerate(labels)]
    return classification_metrics(labels, predictions)


def relation_counts(analyses: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for analysis in analyses:
        for edge in analysis.get("graph", {}).get("edges", []):
            if edge.get("kind") in {"tree_link", "logical_cover"}:
                counts[edge["kind"]] += 1
    return dict(counts)


def levenshtein_distance(left: list[int], right: list[int]) -> int:
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_value in enumerate(left, start=1):
        current = [i]
        for j, right_value in enumerate(right, start=1):
            cost = 0 if left_value == right_value else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def lcs_length(left: list[int], right: list[int]) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    for left_value in left:
        current = [0]
        for index, right_value in enumerate(right, start=1):
            if left_value == right_value:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[index - 1]))
        previous = current
    return previous[-1]


def sequence_similarity_metrics(analyses: Iterable[dict]) -> dict[str, object]:
    per_operation: list[dict[str, object]] = []
    for analysis in analyses:
        for op in analysis.get("operations", []):
            observed = _int_list(op.get("observed_indices", []))
            expected = _int_list(op.get("expected_indices", []))
            if not expected:
                continue
            max_len = max(len(observed), len(expected), 1)
            distance = levenshtein_distance(observed, expected)
            lcs = lcs_length(observed, expected)
            per_operation.append(
                {
                    "op_id": op.get("op_id"),
                    "kind": op.get("kind"),
                    "recognized_as": op.get("recognized_as"),
                    "normalized_levenshtein": distance / max_len,
                    "lcs_similarity": lcs / max_len,
                    "observed_length": len(observed),
                    "expected_length": len(expected),
                }
            )

    if not per_operation:
        return {"operation_count": 0, "average_normalized_levenshtein": 0.0, "average_lcs_similarity": 0.0, "per_operation": []}

    return {
        "operation_count": len(per_operation),
        "average_normalized_levenshtein": sum(float(item["normalized_levenshtein"]) for item in per_operation) / len(per_operation),
        "average_lcs_similarity": sum(float(item["lcs_similarity"]) for item in per_operation) / len(per_operation),
        "per_operation": per_operation,
    }


def relation_metrics(analyses: Iterable[dict]) -> dict[str, object]:
    totals: dict[str, dict[str, int]] = {
        "tree_link": {"tp": 0, "fp": 0, "fn": 0},
        "logical_cover": {"tp": 0, "fp": 0, "fn": 0},
    }

    for analysis in analyses:
        predicted = _predicted_relation_keys(analysis)
        expected = _expected_relation_keys(analysis)
        for kind in totals:
            predicted_kind = {key for key in predicted if key[0] == kind}
            expected_kind = {key for key in expected if key[0] == kind}
            totals[kind]["tp"] += len(predicted_kind & expected_kind)
            totals[kind]["fp"] += len(predicted_kind - expected_kind)
            totals[kind]["fn"] += len(expected_kind - predicted_kind)

    per_kind = {kind: _prf(values["tp"], values["fp"], values["fn"]) for kind, values in totals.items()}
    all_tp = sum(values["tp"] for values in totals.values())
    all_fp = sum(values["fp"] for values in totals.values())
    all_fn = sum(values["fn"] for values in totals.values())
    return {"per_kind": per_kind, "overall": _prf(all_tp, all_fp, all_fn)}


def _predicted_relation_keys(analysis: dict) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()
    for edge in analysis.get("graph", {}).get("edges", []):
        kind = edge.get("kind")
        if kind in {"tree_link", "logical_cover"}:
            result.add((str(kind), str(edge.get("source")), str(edge.get("target"))))
    return result


def _expected_relation_keys(analysis: dict) -> set[tuple[str, str, str]]:
    operation_attrs = _operation_attrs_by_id(analysis)
    result: set[tuple[str, str, str]] = set()
    for op in analysis.get("operations", []):
        expected = _int_list(op.get("expected_indices", []))
        if not expected:
            continue
        array = str(op.get("array", ""))
        recognized_as = op.get("recognized_as")
        if recognized_as == "fenwick_tree":
            for index in expected:
                bit = _lowbit(index)
                if bit <= 0:
                    continue
                result.add(("logical_cover", f"cell:{array}:{index}", f"range:{array}:{index - bit + 1}:{index}"))
        elif recognized_as == "segment_tree":
            attrs = operation_attrs.get(int(op.get("op_id", 0)), {})
            n = int(attrs.get("n") or 0)
            root = int((attrs.get("params") or {}).get("root", 1)) if isinstance(attrs.get("params"), dict) else 1
            nodes = _segment_nodes(n, root=root)
            expected_set = set(expected)
            for index in expected:
                interval = nodes.get(index)
                if interval is None:
                    continue
                left, right = interval
                result.add(("logical_cover", f"cell:{array}:{index}", f"range:{array}:{left}:{right}"))
                left_child = index * 2
                right_child = index * 2 + 1
                if left_child in expected_set:
                    result.add(("tree_link", f"cell:{array}:{index}", f"cell:{array}:{left_child}"))
                if right_child in expected_set:
                    result.add(("tree_link", f"cell:{array}:{index}", f"cell:{array}:{right_child}"))
    return result


def _operation_attrs_by_id(analysis: dict) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for node in analysis.get("graph", {}).get("nodes", []):
        if node.get("label") != "operation":
            continue
        attrs = node.get("attributes", {})
        try:
            op_id = int(attrs.get("op_id"))
        except (TypeError, ValueError):
            continue
        result[op_id] = attrs
    return result


def _segment_nodes(n: int, root: int = 1) -> dict[int, tuple[int, int]]:
    nodes: dict[int, tuple[int, int]] = {}

    def visit(index: int, left: int, right: int) -> None:
        nodes[index] = (left, right)
        if left == right:
            return
        mid = (left + right) // 2
        visit(index * 2, left, mid)
        visit(index * 2 + 1, mid + 1, right)

    if n > 0:
        visit(root, 0, n - 1)
    return nodes


def _prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _lowbit(value: int) -> int:
    return value & -value


def _int_list(values: object) -> list[int]:
    result: list[int] = []
    if not isinstance(values, list):
        return result
    for value in values:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result
