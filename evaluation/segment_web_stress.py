from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from prototype.orchestrator import PipelineOrchestrator


WEB_PATTERN_SOURCES = [
    {
        "name": "cp-algorithms segment tree",
        "url": "https://cp-algorithms.com/data_structures/segment_tree.html",
        "patterns": ["recursive tree", "point update", "range query", "lazy propagation"],
    },
    {
        "name": "CSES Range Queries",
        "url": "https://cses.fi/problemset/list/",
        "patterns": ["range sum", "range minimum", "range update", "point query"],
    },
    {
        "name": "USACO Guide Point Update Range Sum",
        "url": "https://usaco.guide/gold/PURS",
        "patterns": ["point update", "range sum"],
    },
    {
        "name": "Kattis Segment Tree Practice",
        "url": "https://open.kattis.com/contests/ssuidd",
        "patterns": ["contest-style mixed segment tree tasks"],
    },
    {
        "name": "AtCoder Library Practice",
        "url": "https://atcoder.jp/contests/practice2",
        "patterns": ["iterative segment tree style", "monoid range query"],
    },
]


@dataclass
class StressCase:
    name: str
    family: str
    source: str
    input_data: str
    expected_output: str
    check_point_update_order: bool
    pattern_source: str


def combine_expr(op: str, left: str, right: str) -> str:
    if op == "sum":
        return f"({left} + {right})"
    if op == "min":
        return f"std::min({left}, {right})"
    if op == "max":
        return f"std::max({left}, {right})"
    if op == "gcd":
        return f"std::gcd({left}, {right})"
    if op == "xor":
        return f"({left} ^ {right})"
    raise ValueError(op)


def neutral_value(op: str) -> int:
    return {
        "sum": 0,
        "min": 1_000_000_000,
        "max": -1_000_000_000,
        "gcd": 0,
        "xor": 0,
    }[op]


def apply_op(op: str, left: int, right: int) -> int:
    if op == "sum":
        return left + right
    if op == "min":
        return min(left, right)
    if op == "max":
        return max(left, right)
    if op == "gcd":
        import math

        return math.gcd(left, right)
    if op == "xor":
        return left ^ right
    raise ValueError(op)


def sample_point_commands(seed: int, n: int = 8) -> list[tuple[int, ...]]:
    a = seed % n
    b = (seed * 3 + 2) % n
    if a == b:
        b = (b + 1) % n
    c = (seed * 5 + 1) % n
    left = min(a, b, c)
    right = max(a, b, c)
    return [
        (1, a, 5 + seed % 7),
        (1, b, 2 + (seed * 2) % 9),
        (2, left, right),
        (1, c, 3 + (seed * 3) % 11),
        (2, 0, n - 1),
        (2, min(b, c), max(b, c)),
    ]


def expected_point_output(
    op: str,
    commands: list[tuple[int, ...]],
    n: int = 8,
    point_add: bool = False,
    initial: list[int] | None = None,
) -> str:
    arr = list(initial) if initial is not None else [neutral_value(op) for _ in range(n)]
    output: list[str] = []
    for command in commands:
        if command[0] == 1:
            _, pos, value = command
            arr[pos] = apply_op(op, arr[pos], value) if point_add else value
        else:
            _, left, right = command
            value = neutral_value(op)
            for item in arr[left : right + 1]:
                value = apply_op(op, value, item)
            output.append(str(value))
    return "\n".join(output) + ("\n" if output else "")


def point_input(commands: list[tuple[int, ...]], n: int = 8) -> str:
    lines = [f"{n} {len(commands)}"]
    for command in commands:
        lines.append(" ".join(str(item) for item in command))
    return "\n".join(lines) + "\n"


def recursive_point_source(
    op: str,
    *,
    with_n_in_merge: bool,
    point_add: bool,
    one_based_api: bool,
    use_build: bool,
) -> str:
    neutral = neutral_value(op)
    merge_signature = "vector<long long>& seg, int n, int v" if with_n_in_merge else "vector<long long>& seg, int v"
    merge_call = "merge_node(seg, n, v);" if with_n_in_merge else "merge_node(seg, v);"
    update_assignment = (
        f"seg[v] = {combine_expr(op, 'seg[v]', 'value')};"
        if point_add
        else "seg[v] = value;"
    )
    shift_pos = "pos - 1" if one_based_api else "pos"
    shift_left = "left - 1" if one_based_api else "left"
    shift_right = "right - 1" if one_based_api else "right"
    build_block = ""
    build_call = ""
    input_array = ""
    if use_build:
        input_array = "    vector<long long> a(n, 0);\n    for (int i = 0; i < n; ++i) cin >> a[i];\n"
        build_block = f"""
void build_tree(vector<long long>& seg, vector<long long>& a, int n, int v, int l, int r) {{
    if (l == r) {{
        seg[v] = a[l];
        return;
    }}
    int mid = (l + r) / 2;
    build_tree(seg, a, n, v * 2, l, mid);
    build_tree(seg, a, n, v * 2 + 1, mid + 1, r);
    {merge_call}
}}
"""
        build_call = "    build_tree(seg, a, n, 1, 0, n - 1);\n"

    return f"""
#include <bits/stdc++.h>
using namespace std;

long long combine_value(long long left_value, long long right_value) {{
    return {combine_expr(op, 'left_value', 'right_value')};
}}

void merge_node({merge_signature}) {{
    seg[v] = combine_value(seg[v * 2], seg[v * 2 + 1]);
}}
{build_block}
void update_impl(vector<long long>& seg, int n, int v, int l, int r, int pos, long long value) {{
    if (l == r) {{
        {update_assignment}
        return;
    }}
    int mid = (l + r) / 2;
    if (pos <= mid) update_impl(seg, n, v * 2, l, mid, pos, value);
    else update_impl(seg, n, v * 2 + 1, mid + 1, r, pos, value);
    {merge_call}
}}

long long query_impl(vector<long long>& seg, int n, int v, int l, int r, int ql, int qr) {{
    if (qr < l || r < ql) return {neutral};
    if (ql <= l && r <= qr) return seg[v];
    int mid = (l + r) / 2;
    long long left_answer = query_impl(seg, n, v * 2, l, mid, ql, qr);
    long long right_answer = query_impl(seg, n, v * 2 + 1, mid + 1, r, ql, qr);
    return combine_value(left_answer, right_answer);
}}

void update(vector<long long>& seg, int n, int pos, long long value) {{
    update_impl(seg, n, 1, 0, n - 1, {shift_pos}, value);
}}

long long query(vector<long long>& seg, int n, int left, int right) {{
    return query_impl(seg, n, 1, 0, n - 1, {shift_left}, {shift_right});
}}

int main() {{
    int n, q;
    cin >> n >> q;
    vector<long long> seg(4 * n, {neutral});
{input_array}{build_call}    while (q--) {{
        int type;
        cin >> type;
        if (type == 1) {{
            int pos;
            long long value;
            cin >> pos >> value;
            update(seg, n, pos, value);
        }} else {{
            int left, right;
            cin >> left >> right;
            cout << query(seg, n, left, right) << "\\n";
        }}
    }}
    return 0;
}}
""".strip()


def c_array_point_source(op: str) -> str:
    neutral = neutral_value(op)
    return f"""
#include <bits/stdc++.h>
using namespace std;

long long seg[128];

long long combine_value(long long left_value, long long right_value) {{
    return {combine_expr(op, 'left_value', 'right_value')};
}}

void merge_node(int v) {{
    seg[v] = combine_value(seg[v * 2], seg[v * 2 + 1]);
}}

void update_impl(int n, int v, int l, int r, int pos, long long value) {{
    if (l == r) {{
        seg[v] = value;
        return;
    }}
    int mid = (l + r) / 2;
    if (pos <= mid) update_impl(n, v * 2, l, mid, pos, value);
    else update_impl(n, v * 2 + 1, mid + 1, r, pos, value);
    merge_node(v);
}}

long long query_impl(int n, int v, int l, int r, int ql, int qr) {{
    if (qr < l || r < ql) return {neutral};
    if (ql <= l && r <= qr) return seg[v];
    int mid = (l + r) / 2;
    return combine_value(query_impl(n, v * 2, l, mid, ql, qr), query_impl(n, v * 2 + 1, mid + 1, r, ql, qr));
}}

void update(int n, int pos, long long value) {{
    update_impl(n, 1, 0, n - 1, pos, value);
}}

long long query(int n, int left, int right) {{
    return query_impl(n, 1, 0, n - 1, left, right);
}}

int main() {{
    int n, q;
    cin >> n >> q;
    while (q--) {{
        int type;
        cin >> type;
        if (type == 1) {{
            int pos;
            long long value;
            cin >> pos >> value;
            update(n, pos, value);
        }} else {{
            int left, right;
            cin >> left >> right;
            cout << query(n, left, right) << "\\n";
        }}
    }}
    return 0;
}}
""".strip()


def iterative_point_source(op: str) -> str:
    neutral = neutral_value(op)
    return f"""
#include <bits/stdc++.h>
using namespace std;

long long merge_value(long long left_value, long long right_value) {{
    return {combine_expr(op, 'left_value', 'right_value')};
}}

void build_segment_tree(vector<long long>& seg, int n) {{
    for (int v = n - 1; v > 0; --v) {{
        seg[v] = merge_value(seg[v * 2], seg[v * 2 + 1]);
    }}
}}

void update(vector<long long>& seg, int n, int pos, long long value) {{
    pos += n;
    seg[pos] = value;
    for (pos /= 2; pos >= 1; pos /= 2) {{
        seg[pos] = merge_value(seg[pos * 2], seg[pos * 2 + 1]);
        if (pos == 1) break;
    }}
}}

long long query(vector<long long>& seg, int n, int left, int right) {{
    long long answer_left = {neutral};
    long long answer_right = {neutral};
    left += n;
    right += n + 1;
    while (left < right) {{
        if (left & 1) answer_left = merge_value(answer_left, seg[left++]);
        if (right & 1) answer_right = merge_value(seg[--right], answer_right);
        left /= 2;
        right /= 2;
    }}
    return merge_value(answer_left, answer_right);
}}

int main() {{
    int n, q;
    cin >> n >> q;
    vector<long long> seg(2 * n, {neutral});
    build_segment_tree(seg, n);
    while (q--) {{
        int type;
        cin >> type;
        if (type == 1) {{
            int pos;
            long long value;
            cin >> pos >> value;
            update(seg, n, pos, value);
        }} else {{
            int left, right;
            cin >> left >> right;
            cout << query(seg, n, left, right) << "\\n";
        }}
    }}
    return 0;
}}
""".strip()


def lazy_add_source() -> str:
    return """
#include <bits/stdc++.h>
using namespace std;

void apply_node(vector<long long>& seg, vector<long long>& lazy, int v, int l, int r, long long delta) {
    seg[v] += delta * (r - l + 1);
    lazy[v] += delta;
}

void push_node(vector<long long>& seg, vector<long long>& lazy, int v, int l, int r) {
    if (lazy[v] == 0 || l == r) return;
    int mid = (l + r) / 2;
    apply_node(seg, lazy, v * 2, l, mid, lazy[v]);
    apply_node(seg, lazy, v * 2 + 1, mid + 1, r, lazy[v]);
    lazy[v] = 0;
}

void range_add(vector<long long>& seg, vector<long long>& lazy, int n, int v, int l, int r, int ql, int qr, long long delta) {
    if (qr < l || r < ql) return;
    if (ql <= l && r <= qr) {
        apply_node(seg, lazy, v, l, r, delta);
        return;
    }
    push_node(seg, lazy, v, l, r);
    int mid = (l + r) / 2;
    range_add(seg, lazy, n, v * 2, l, mid, ql, qr, delta);
    range_add(seg, lazy, n, v * 2 + 1, mid + 1, r, ql, qr, delta);
    seg[v] = seg[v * 2] + seg[v * 2 + 1];
}

long long query(vector<long long>& seg, vector<long long>& lazy, int n, int v, int l, int r, int ql, int qr) {
    if (qr < l || r < ql) return 0;
    if (ql <= l && r <= qr) return seg[v];
    push_node(seg, lazy, v, l, r);
    int mid = (l + r) / 2;
    return query(seg, lazy, n, v * 2, l, mid, ql, qr) + query(seg, lazy, n, v * 2 + 1, mid + 1, r, ql, qr);
}

int main() {
    int n, q;
    cin >> n >> q;
    vector<long long> seg(4 * n, 0);
    vector<long long> lazy(4 * n, 0);
    while (q--) {
        int type;
        cin >> type;
        if (type == 1) {
            int left, right;
            long long delta;
            cin >> left >> right >> delta;
            range_add(seg, lazy, n, 1, 0, n - 1, left, right, delta);
        } else {
            int left, right;
            cin >> left >> right;
            cout << query(seg, lazy, n, 1, 0, n - 1, left, right) << "\\n";
        }
    }
    return 0;
}
""".strip()


def lazy_input(seed: int, n: int = 8) -> tuple[str, str]:
    commands = [
        (1, seed % n, min(n - 1, seed % n + 2), 3 + seed % 5),
        (1, 0, n - 1, 1),
        (2, 0, n - 1),
        (1, 2, 5, 2),
        (2, 3, 6),
        (2, seed % n, seed % n),
    ]
    arr = [0] * n
    output: list[str] = []
    for command in commands:
        if command[0] == 1:
            _, left, right, delta = command
            for index in range(left, right + 1):
                arr[index] += delta
        else:
            _, left, right = command
            output.append(str(sum(arr[left : right + 1])))
    lines = [f"{n} {len(commands)}", *(" ".join(map(str, command)) for command in commands)]
    return "\n".join(lines) + "\n", "\n".join(output) + "\n"


def build_cases() -> list[StressCase]:
    cases: list[StressCase] = []
    ops = ["sum", "min", "max", "gcd", "xor"]
    case_no = 1

    for op in ops:
        for with_n in [True, False]:
            for point_add in [False, True]:
                for one_based in [False, True]:
                    commands = sample_point_commands(case_no)
                    if one_based:
                        commands = [
                            (item[0], item[1] + 1, item[2]) if item[0] == 1 else (item[0], item[1] + 1, item[2] + 1)
                            for item in commands
                        ]
                    expected_commands = [
                        (item[0], item[1] - 1, item[2]) if one_based and item[0] == 1 else
                        (item[0], item[1] - 1, item[2] - 1) if one_based else item
                        for item in commands
                    ]
                    cases.append(
                        StressCase(
                            name=f"recursive_{op}_{case_no:03d}",
                            family="recursive_point",
                            source=recursive_point_source(op, with_n_in_merge=with_n, point_add=point_add, one_based_api=one_based, use_build=False),
                            input_data=point_input(commands),
                            expected_output=expected_point_output(op, expected_commands, point_add=point_add),
                            check_point_update_order=True,
                            pattern_source="cp-algorithms / USACO PURS style",
                        )
                    )
                    case_no += 1

    for op in ops:
        for seed in range(4):
            commands = sample_point_commands(case_no + seed)
            initial = [1, 2, 3, 4, 5, 6, 7, 8]
            cases.append(
                StressCase(
                    name=f"build_{op}_{case_no:03d}",
                    family="recursive_build",
                    source=recursive_point_source(op, with_n_in_merge=seed % 2 == 0, point_add=False, one_based_api=False, use_build=True),
                    input_data=point_input(commands).replace("\n", "\n1 2 3 4 5 6 7 8\n", 1),
                    expected_output=expected_point_output(op, commands, initial=initial),
                    check_point_update_order=True,
                    pattern_source="CSES static/dynamic range queries style",
                )
            )
            case_no += 1

    for op in ["sum", "gcd", "xor"]:
        for seed in range(5):
            commands = sample_point_commands(case_no + seed)
            cases.append(
                StressCase(
                    name=f"c_array_{op}_{case_no:03d}",
                    family="global_c_array",
                    source=c_array_point_source(op),
                    input_data=point_input(commands),
                    expected_output=expected_point_output(op, commands),
                    check_point_update_order=True,
                    pattern_source="Kattis/global-array contest style",
                )
            )
            case_no += 1

    for op in ops:
        for seed in range(4):
            commands = sample_point_commands(case_no + seed)
            cases.append(
                StressCase(
                    name=f"iterative_{op}_{case_no:03d}",
                    family="iterative_tree",
                    source=iterative_point_source(op),
                    input_data=point_input(commands),
                    expected_output=expected_point_output(op, commands),
                    check_point_update_order=False,
                    pattern_source="AtCoder Library iterative segment tree style",
                )
            )
            case_no += 1

    for seed in range(5):
        input_data, expected = lazy_input(seed)
        cases.append(
            StressCase(
                name=f"lazy_add_sum_{case_no:03d}",
                family="lazy_range_add",
                source=lazy_add_source(),
                input_data=input_data,
                expected_output=expected,
                check_point_update_order=False,
                pattern_source="cp-algorithms lazy propagation / CSES range update style",
            )
        )
        case_no += 1

    return cases[:100]


def range_size(node_state: dict[str, Any] | None) -> int | None:
    if not node_state:
        return None
    interval = node_state.get("range")
    if not isinstance(interval, list) or len(interval) != 2:
        return None
    try:
        return int(interval[1]) - int(interval[0]) + 1
    except (TypeError, ValueError):
        return None


def point_update_order_violations(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for op in analysis.get("operations", []):
        if op.get("kind") != "segment_update":
            continue
        op_id = op.get("op_id")
        write_sizes: list[int] = []
        write_nodes: list[str] = []
        for step in analysis.get("tree_timeline", {}).get("steps", []):
            mutation = step.get("mutation") or {}
            if step.get("op_id") != op_id or mutation.get("mode") != "write":
                continue
            size = range_size(step.get("node_state"))
            if size is None:
                continue
            write_sizes.append(size)
            write_nodes.append(str(step.get("node_id")))
        if len(write_sizes) > 1 and any(write_sizes[index] > write_sizes[index + 1] for index in range(len(write_sizes) - 1)):
            violations.append({"op_id": op_id, "nodes": write_nodes, "range_sizes": write_sizes})
    return violations


def run_stress(output_dir: Path = Path("prototype/build/segment_web_stress")) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    orchestrator = PipelineOrchestrator(output_dir / "runs")
    results: list[dict[str, Any]] = []

    for case in cases:
        result = orchestrator.execute(case.source, {"auto_detect": True, "limits": {"timeout_seconds": 5}}, case.input_data, run_id=case.name)
        case_dir = output_dir / "cases" / case.name
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "source.cpp").write_text(case.source, encoding="utf-8")
        (case_dir / "input.txt").write_text(case.input_data, encoding="utf-8")
        (case_dir / "expected_output.txt").write_text(case.expected_output, encoding="utf-8")
        stdout = str(result.run.get("stdout", ""))
        output_ok = result.status == "success" and stdout == case.expected_output
        violations = point_update_order_violations(result.analysis) if result.status == "success" and case.check_point_update_order else []
        findings = [finding.get("code") for finding in result.analysis.get("findings", [])]
        recognized = sorted({op.get("recognized_as") for op in result.analysis.get("operations", []) if op.get("recognized_as")})
        item = {
            **asdict(case),
            "status": result.status,
            "stdout": stdout,
            "output_ok": output_ok,
            "errors": result.errors,
            "recognized": recognized,
            "finding_codes": findings,
            "point_update_order_violations": violations,
            "artifacts": result.artifacts,
            "run": result.run,
            "effective_config": result.instrumentation.get("effective_config", {}),
        }
        results.append(item)

    summary = {
        "case_count": len(cases),
        "web_pattern_sources": WEB_PATTERN_SOURCES,
        "status_counts": _counts(item["status"] for item in results),
        "family_counts": _counts(item["family"] for item in results),
        "output_mismatch_count": sum(1 for item in results if not item["output_ok"]),
        "compile_error_count": sum(1 for item in results if item["status"] == "compile_error"),
        "runtime_error_count": sum(1 for item in results if item["status"] == "runtime_error"),
        "timeout_count": sum(1 for item in results if item["status"] == "timeout"),
        "point_update_order_violation_count": sum(1 for item in results if item["point_update_order_violations"]),
        "non_segment_recognition_count": sum(1 for item in results if "segment_tree" not in item["recognized"]),
        "results": results,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    summary = run_stress()
    printable = {key: value for key, value in summary.items() if key != "results"}
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    print("wrote prototype/build/segment_web_stress/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
