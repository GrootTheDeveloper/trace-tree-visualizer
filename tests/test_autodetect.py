from __future__ import annotations

from prototype.evaluation.dataset import bracket_pairs_source, fenwick_source, non_target_source, segment_source
from prototype.instrumenter.autodetect import detect_config


def test_autodetect_segment_tree_config() -> None:
    config = detect_config(segment_source(False))

    assert config["target_arrays"][0]["name"] == "seg"
    assert config["target_arrays"][0]["structure_type"] == "segment_tree"
    assert config["tree_model"]["seg"]["node_variable"] == "v"
    operation_names = {operation["function_name"]: operation for operation in config["operations"]}
    assert operation_names["update"]["operation_type"] == "update"
    assert operation_names["update_impl"]["operation_type"] == "update"
    assert operation_names["update_impl"]["param_roles"] == {"node": "v", "lo": "l", "hi": "r", "pos": "pos"}
    assert operation_names["merge_node"]["operation_type"] == "merge"


def test_autodetect_global_one_based_segment_tree_config() -> None:
    source = """
#include <bits/stdc++.h>
using namespace std;

int n, q;
long long a[100005];
long long seg[400020];

void build(int id, int l, int r) {
    if (l == r) {
        seg[id] = a[l];
        return;
    }
    int mid = (l + r) / 2;
    build(id * 2, l, mid);
    build(id * 2 + 1, mid + 1, r);
    seg[id] = seg[id * 2] + seg[id * 2 + 1];
}

void update(int id, int l, int r, int pos, long long value) {
    if (l == r) {
        seg[id] = value;
        return;
    }
    int mid = (l + r) / 2;
    if (pos <= mid) update(id * 2, l, mid, pos, value);
    else update(id * 2 + 1, mid + 1, r, pos, value);
    seg[id] = seg[id * 2] + seg[id * 2 + 1];
}

long long query(int id, int l, int r, int u, int v) {
    if (v < l || r < u) return 0;
    if (u <= l && r <= v) return seg[id];
    int mid = (l + r) / 2;
    return query(id * 2, l, mid, u, v) + query(id * 2 + 1, mid + 1, r, u, v);
}

int main() {
    cin >> n >> q;
    build(1, 1, n);
}
"""
    config = detect_config(source)
    operations = {operation["function_name"]: operation for operation in config["operations"]}

    assert config["target_arrays"][0]["name"] == "seg"
    assert config["target_arrays"][1]["name"] == "a"
    assert config["target_arrays"][1]["role"] == "base_array"
    assert config["tree_model"]["seg"]["base_array"] == "a"
    assert config["target_arrays"][0]["index_base"] == 1
    assert config["tree_model"]["seg"]["node_variable"] == "id"
    assert operations["build"]["operation_type"] == "build"
    assert operations["build"]["param_roles"] == {"node": "id", "lo": "l", "hi": "r"}
    assert operations["update"]["operation_type"] == "update"
    assert operations["update"]["params"] == ["pos"]
    assert operations["update"]["param_roles"] == {"node": "id", "lo": "l", "hi": "r", "pos": "pos"}
    assert operations["query"]["operation_type"] == "query"
    assert operations["query"]["params"] == ["u", "v"]
    assert operations["query"]["param_roles"] == {"node": "id", "lo": "l", "hi": "r", "ql": "u", "qr": "v"}


def test_autodetect_multiple_recursive_segment_trees() -> None:
    source = """
#include <bits/stdc++.h>
using namespace std;

int n;
long long a[100], sumTree[400], maxTree[400];

void build_sum(int id, int l, int r) {
    if (l == r) { sumTree[id] = a[l]; return; }
    int mid = (l + r) / 2;
    build_sum(id * 2, l, mid);
    build_sum(id * 2 + 1, mid + 1, r);
    sumTree[id] = sumTree[id * 2] + sumTree[id * 2 + 1];
}

void build_max(int id, int l, int r) {
    if (l == r) { maxTree[id] = a[l]; return; }
    int mid = (l + r) / 2;
    build_max(id * 2, l, mid);
    build_max(id * 2 + 1, mid + 1, r);
    maxTree[id] = max(maxTree[id * 2], maxTree[id * 2 + 1]);
}

int main() {
    cin >> n;
    for (int i = 1; i <= n; i++) cin >> a[i];
    build_sum(1, 1, n);
    build_max(1, 1, n);
}
"""
    config = detect_config(source)
    arrays = [item["name"] for item in config["target_arrays"]]
    operations = {(item["target_array"], item["function_name"]): item for item in config["operations"]}

    assert {"sumTree", "maxTree"} <= set(arrays)
    assert "a" in arrays
    assert config["tree_model"]["sumTree"]["base_array"] == "a"
    assert config["tree_model"]["maxTree"]["base_array"] == "a"
    assert {item["array"] for item in config["tree_instances"]} == {"sumTree", "maxTree"}
    assert operations[("sumTree", "build_sum")]["param_roles"] == {"node": "id", "lo": "l", "hi": "r"}
    assert operations[("maxTree", "build_max")]["param_roles"] == {"node": "id", "lo": "l", "hi": "r"}


def test_autodetect_lazy_array_as_parallel_field() -> None:
    source = """
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
"""
    config = detect_config(source)

    assert {item["array"] for item in config["tree_instances"]} == {"seg"}
    assert {"array": "lazy", "field": "lazy", "role": "lazy_field"} in config["tree_model"]["seg"]["node_fields"]
    lazy_target = next(item for item in config["target_arrays"] if item["name"] == "lazy")
    assert lazy_target["role"] == "lazy_field"
    assert lazy_target["source_for"] == "seg"
    operations = {item["function_name"]: item for item in config["operations"]}
    assert operations["range_add"]["operation_type"] == "update"


def test_autodetect_segment_tree_roles_do_not_depend_on_variable_names() -> None:
    source = """
#include <bits/stdc++.h>
using namespace std;

int n;
long long t[400];

void make(int i, int s, int e) {
    if (s == e) {
        t[i] = 0;
        return;
    }
    int m = (s + e) / 2;
    make(i << 1, s, m);
    make(i << 1 | 1, m + 1, e);
    t[i] = t[i << 1] + t[i << 1 | 1];
}

void chg(int i, int s, int e, int x, long long y) {
    if (s == e) {
        t[i] = y;
        return;
    }
    int m = (s + e) / 2;
    if (x <= m) chg(i << 1, s, m, x, y);
    else chg(i << 1 | 1, m + 1, e, x, y);
    t[i] = t[i << 1] + t[i << 1 | 1];
}

long long ask(int i, int s, int e, int a, int b) {
    if (b < s || e < a) return 0;
    if (a <= s && e <= b) return t[i];
    int m = (s + e) / 2;
    return ask(i << 1, s, m, a, b) + ask(i << 1 | 1, m + 1, e, a, b);
}

int main() {
    make(1, 0, n - 1);
}
"""
    config = detect_config(source)
    operations = {operation["function_name"]: operation for operation in config["operations"]}

    assert config["detected"]["role_inference"] == "ast"
    assert config["target_arrays"][0]["name"] == "t"
    assert operations["make"]["operation_type"] == "build"
    assert operations["make"]["param_roles"] == {"node": "i", "lo": "s", "hi": "e"}
    assert operations["chg"]["operation_type"] == "update"
    assert operations["chg"]["param_roles"] == {"node": "i", "lo": "s", "hi": "e", "pos": "x"}
    assert operations["ask"]["operation_type"] == "query"
    assert operations["ask"]["param_roles"] == {"node": "i", "lo": "s", "hi": "e", "ql": "a", "qr": "b"}


def test_autodetect_fenwick_config() -> None:
    config = detect_config(fenwick_source(False))

    assert config["target_arrays"][0]["name"] == "bit"
    assert config["target_arrays"][0]["structure_type"] == "fenwick"
    assert config["target_arrays"][0]["index_base"] == 1
    operation_types = {operation["function_name"]: operation["operation_type"] for operation in config["operations"]}
    assert operation_types["add"] == "update"
    assert operation_types["sum"] == "query"


def test_autodetect_bracket_pairs_as_array() -> None:
    config = detect_config(bracket_pairs_source())

    assert config["target_arrays"][0]["name"] == "match"
    assert config["target_arrays"][0]["structure_type"] == "array"
    assert config["operations"][0]["function_name"] == "match_pairs"


def test_autodetect_non_target_array() -> None:
    config = detect_config(non_target_source())

    assert config["target_arrays"][0]["name"] == "arr"
    assert config["target_arrays"][0]["structure_type"] == "array"
