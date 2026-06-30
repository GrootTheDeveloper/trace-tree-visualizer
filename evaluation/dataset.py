from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DatasetCase:
    name: str
    label: str
    source: str
    config: dict[str, Any]
    input_data: str = ""
    bug_lines: list[int] = field(default_factory=list)
    bug_markers: list[str] = field(default_factory=list)
    expected_findings: list[str] | None = None
    expected_relations: dict[str, list[dict[str, Any]]] | None = None
    is_real_world: bool = False
    source_family: str = "synthetic"


def fenwick_source(
    bad_lowbit: bool = False,
    n: int = 8,
    first_pos: int = 3,
    second_pos: int = 4,
    query_pos: int = 7,
    marker: str = "BUG_LOWBIT",
) -> str:
    step = f"(i & -i) + 1 /* {marker} */" if bad_lowbit else "(i & -i)"
    access_marker = f" /* {marker} */" if bad_lowbit else ""
    return f"""
#include <bits/stdc++.h>
using namespace std;

void add(vector<int>& bit, int n, int pos, int delta) {{
    for (int i = pos; i <= n; i += {step}) {{
        bit[i] += delta;{access_marker}
    }}
}}

int sum(vector<int>& bit, int pos) {{
    int ans = 0;
    for (int i = pos; i > 0; i -= (i & -i)) {{
        ans += bit[i];
    }}
    return ans;
}}

int main() {{
    int n = {n};
    vector<int> bit(n + 1, 0);
    add(bit, n, {first_pos}, 5);
    add(bit, n, {second_pos}, 2);
    cout << sum(bit, {query_pos}) << "\\n";
    return 0;
}}
""".strip()


def segment_source(
    bad_merge: bool = False,
    n: int = 8,
    first_pos: int = 3,
    second_pos: int = 5,
    marker: str = "BUG_BAD_MERGE",
) -> str:
    right_child = f"v * 2 /* {marker} */" if bad_merge else "v * 2 + 1"
    return f"""
#include <bits/stdc++.h>
using namespace std;

void merge_node(vector<int>& seg, int n, int v) {{
    seg[v] = seg[v * 2] + seg[{right_child}];
}}

void update_impl(vector<int>& seg, int n, int v, int l, int r, int pos, int value) {{
    if (l == r) {{
        seg[v] = value;
        return;
    }}
    int mid = (l + r) / 2;
    if (pos <= mid) update_impl(seg, n, v * 2, l, mid, pos, value);
    else update_impl(seg, n, v * 2 + 1, mid + 1, r, pos, value);
    merge_node(seg, n, v);
}}

void update(vector<int>& seg, int n, int pos, int value) {{
    update_impl(seg, n, 1, 0, n - 1, pos, value);
}}

int main() {{
    int n = {n};
    vector<int> seg(4 * n, 0);
    update(seg, n, {first_pos}, 7);
    update(seg, n, {second_pos}, 4);
    cout << seg[1] << "\\n";
    return 0;
}}
""".strip()


def non_target_source(n: int = 5, initial: int = 1) -> str:
    return f"""
#include <bits/stdc++.h>
using namespace std;

void scan(vector<int>& arr, int n) {{
    for (int i = 1; i < n; ++i) {{
        arr[i] += arr[i - 1];
    }}
}}

int main() {{
    int n = {n};
    vector<int> arr(n, {initial});
    scan(arr, n);
    cout << arr[n - 1] << "\\n";
    return 0;
}}
""".strip()


def bracket_pairs_source() -> str:
    return """
#include <bits/stdc++.h>
using namespace std;

void match_pairs(vector<int>& match, const string& s, int n) {
    vector<int> st;
    for (int i = 0; i < n; ++i) {
        char c = s[i];
        if (c == '(') {
            st.push_back(i);
        } else if (c == ')' && !st.empty()) {
            int open = st.back();
            st.pop_back();
            match[open] = i;
            match[i] = open;
        }
    }
}

int main() {
    string s;
    cin >> s;
    int n = (int)s.size();
    vector<int> match(n, -1);
    match_pairs(match, s, n);
    for (int i = 0; i < n; ++i) {
        cout << i << ":" << match[i] << "\\n";
    }
    return 0;
}
""".strip()


def global_fenwick_source() -> str:
    return """
#include <bits/stdc++.h>
using namespace std;

int bit[64];

void add(int n, int pos, int delta) {
    for (int i = pos; i <= n; i += (i & -i)) bit[i] += delta;
}

int pref(int pos) {
    int answer = 0;
    for (int i = pos; i > 0; i -= (i & -i)) answer += bit[i];
    return answer;
}

int main() {
    int n = 12;
    add(n, 2, 3);
    add(n, 9, 4);
    cout << pref(10) << "\\n";
    return 0;
}
""".strip()


def compact_segment_source() -> str:
    return """
#include <bits/stdc++.h>
using namespace std;

int seg[128];

void merge_node(int n, int v) {
    seg[v] = seg[v * 2] + seg[v * 2 + 1];
}

void update_impl(int n, int v, int l, int r, int pos, int value) {
    if (l == r) {
        seg[v] = value;
        return;
    }
    int mid = (l + r) / 2;
    if (pos <= mid) update_impl(n, v * 2, l, mid, pos, value);
    else update_impl(n, v * 2 + 1, mid + 1, r, pos, value);
    merge_node(n, v);
}

void update(int n, int pos, int value) {
    update_impl(n, 1, 0, n - 1, pos, value);
}

int main() {
    int n = 10;
    update(n, 4, 6);
    update(n, 8, 1);
    cout << seg[1] << "\\n";
    return 0;
}
""".strip()


def frequency_table_source() -> str:
    return """
#include <bits/stdc++.h>
using namespace std;

void count_values(vector<int>& freq, int n) {
    vector<int> a = {1, 3, 1, 2, 3, 3};
    for (int x : a) {
        freq[x] += 1;
    }
}

int main() {
    int n = 6;
    vector<int> freq(8, 0);
    count_values(freq, n);
    cout << freq[3] << "\\n";
    return 0;
}
""".strip()


def fenwick_config() -> dict[str, Any]:
    return {
        "target_arrays": [{"name": "bit", "structure_type": "fenwick", "index_base": 1, "size_variable": "n"}],
        "operations": [
            {"function_name": "add", "operation_type": "update", "target_array": "bit", "params": ["pos"], "logical_size": "n"},
            {"function_name": "sum", "operation_type": "query", "target_array": "bit", "params": ["pos"], "logical_size": "pos"},
        ],
        "limits": {"timeout_seconds": 5},
    }


def global_fenwick_config() -> dict[str, Any]:
    config = fenwick_config()
    config["operations"][1]["function_name"] = "pref"
    return config


def segment_config() -> dict[str, Any]:
    return {
        "target_arrays": [{"name": "seg", "structure_type": "segment_tree", "index_base": 0, "size_variable": "n"}],
        "operations": [
            {"function_name": "update", "operation_type": "update", "target_array": "seg", "params": ["pos"], "logical_size": "n"},
            {"function_name": "merge_node", "operation_type": "merge", "target_array": "seg", "params": ["v"], "logical_size": "n"},
        ],
        "limits": {"timeout_seconds": 5},
    }


def non_target_config(array_name: str = "arr", function_name: str = "scan") -> dict[str, Any]:
    return {
        "target_arrays": [{"name": array_name, "structure_type": "array", "index_base": 0, "size_variable": "n"}],
        "operations": [{"function_name": function_name, "operation_type": "scan", "target_array": array_name, "params": [], "logical_size": "n"}],
        "limits": {"timeout_seconds": 5},
    }


def bracket_pairs_config() -> dict[str, Any]:
    return {
        "target_arrays": [{"name": "match", "structure_type": "array", "index_base": 0, "size_variable": "n"}],
        "operations": [
            {"function_name": "match_pairs", "operation_type": "scan", "target_array": "match", "params": [], "logical_size": "n"}
        ],
        "watch_expressions": ["i", "c", "st.size()", "s[i]", "open"],
        "limits": {"timeout_seconds": 5},
    }


def frequency_config() -> dict[str, Any]:
    return non_target_config(array_name="freq", function_name="count_values")


def default_dataset() -> list[DatasetCase]:
    cases: list[DatasetCase] = []

    fenwick_variants = [
        (8, 3, 4, 7),
        (8, 2, 6, 6),
        (10, 5, 9, 9),
        (12, 1, 8, 11),
        (16, 7, 13, 15),
        (6, 2, 5, 5),
    ]
    for index, (n, first, second, query) in enumerate(fenwick_variants, start=1):
        cases.append(
            DatasetCase(
                f"fenwick_ok_{index:02d}",
                "fenwick_tree",
                fenwick_source(False, n=n, first_pos=first, second_pos=second, query_pos=query),
                fenwick_config(),
                source_family="synthetic_fenwick",
            )
        )

    segment_variants = [
        (8, 3, 5),
        (8, 1, 6),
        (10, 4, 8),
        (7, 2, 5),
        (12, 6, 10),
        (6, 0, 4),
    ]
    for index, (n, first, second) in enumerate(segment_variants, start=1):
        cases.append(
            DatasetCase(
                f"segment_ok_{index:02d}",
                "segment_tree",
                segment_source(False, n=n, first_pos=first, second_pos=second),
                segment_config(),
                source_family="synthetic_segment",
            )
        )

    for index, (n, initial) in enumerate([(5, 1), (6, 2), (8, 1), (9, 3), (4, 5)], start=1):
        cases.append(
            DatasetCase(
                f"non_target_{index:02d}",
                "non_target_unknown",
                non_target_source(n=n, initial=initial),
                non_target_config(),
                source_family="synthetic_non_target",
            )
        )
    cases.append(
        DatasetCase(
            "bracket_pairs_01",
            "non_target_unknown",
            bracket_pairs_source(),
            bracket_pairs_config(),
            input_data="(()())\n",
            source_family="synthetic_non_target",
        )
    )

    real_world_style = [
        DatasetCase("real_style_fenwick_global", "fenwick_tree", global_fenwick_source(), global_fenwick_config(), is_real_world=True, source_family="real_world_style"),
        DatasetCase("real_style_segment_global", "segment_tree", compact_segment_source(), segment_config(), is_real_world=True, source_family="real_world_style"),
        DatasetCase("real_style_frequency_table", "non_target_unknown", frequency_table_source(), frequency_config(), is_real_world=True, source_family="real_world_style"),
        DatasetCase("real_style_prefix_scan", "non_target_unknown", non_target_source(n=11, initial=2), non_target_config(), is_real_world=True, source_family="real_world_style"),
        DatasetCase("real_style_bracket_pairs", "non_target_unknown", bracket_pairs_source(), bracket_pairs_config(), input_data="()(()())\n", is_real_world=True, source_family="real_world_style"),
    ]
    cases.extend(real_world_style)

    for index, (n, first, second, query) in enumerate([(8, 3, 4, 7), (10, 2, 6, 8), (12, 5, 9, 11), (16, 7, 13, 15), (6, 2, 5, 5)], start=1):
        marker = f"BUG_LOWBIT_{index}"
        cases.append(
            DatasetCase(
                f"fenwick_bad_lowbit_{index:02d}",
                "fenwick_tree",
                fenwick_source(True, n=n, first_pos=first, second_pos=second, query_pos=query, marker=marker),
                fenwick_config(),
                bug_markers=[marker],
                expected_findings=["FENWICK_BAD_INDEX_SEQUENCE"],
                source_family="mutant_fenwick",
            )
        )

    for index, (n, first, second) in enumerate([(8, 3, 5), (8, 1, 6), (10, 4, 8), (7, 2, 5), (12, 6, 10)], start=1):
        marker = f"BUG_BAD_MERGE_{index}"
        cases.append(
            DatasetCase(
                f"segment_bad_merge_{index:02d}",
                "segment_tree",
                segment_source(True, n=n, first_pos=first, second_pos=second, marker=marker),
                segment_config(),
                bug_markers=[marker],
                expected_findings=["SEGMENT_BAD_MERGE_CHILDREN"],
                source_family="mutant_segment",
            )
        )

    return cases
