from __future__ import annotations

from pathlib import Path

from prototype.evaluation.dataset import fenwick_config, fenwick_source, segment_config, segment_source
from prototype.orchestrator import PipelineOrchestrator


GLOBAL_ONE_BASED_SEGMENT_SOURCE = """
#include <bits/stdc++.h>
using namespace std;

const int MAXN = 100005;

int n, q;
long long a[MAXN];
long long seg[4 * MAXN];

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

    if (pos <= mid) {
        update(id * 2, l, mid, pos, value);
    } else {
        update(id * 2 + 1, mid + 1, r, pos, value);
    }

    seg[id] = seg[id * 2] + seg[id * 2 + 1];
}

long long query(int id, int l, int r, int u, int v) {
    if (v < l || r < u) {
        return 0;
    }

    if (u <= l && r <= v) {
        return seg[id];
    }

    int mid = (l + r) / 2;

    long long leftSum = query(id * 2, l, mid, u, v);
    long long rightSum = query(id * 2 + 1, mid + 1, r, u, v);

    return leftSum + rightSum;
}

int main() {
    cin >> n >> q;

    for (int i = 1; i <= n; i++) {
        cin >> a[i];
    }

    build(1, 1, n);

    while (q--) {
        int type;
        cin >> type;

        if (type == 1) {
            int pos;
            long long value;
            cin >> pos >> value;

            update(1, 1, n, pos, value);
        } else if (type == 2) {
            int l, r;
            cin >> l >> r;

            cout << query(1, 1, n, l, r) << '\\n';
        }
    }

    return 0;
}
""".strip()


def test_fenwick_end_to_end(tmp_path: Path) -> None:
    result = PipelineOrchestrator(tmp_path / "runs").execute(fenwick_source(), fenwick_config(), run_id="fenwick")
    assert result.status == "success"
    assert result.analysis["summary"]["operation_count"] >= 3
    assert result.analysis["graph"]["summary"]["node_count"] > 0


def test_segment_tree_end_to_end(tmp_path: Path) -> None:
    result = PipelineOrchestrator(tmp_path / "runs").execute(segment_source(), segment_config(), run_id="segment")
    assert result.status == "success"
    assert result.analysis["summary"]["operation_count"] >= 2
    assert any(op["recognized_as"] == "segment_tree" for op in result.analysis["operations"])


def test_segment_tree_watch_does_not_split_if_else(tmp_path: Path) -> None:
    config = segment_config()
    config["watch_expressions"] = ["pos", "v"]
    result = PipelineOrchestrator(tmp_path / "runs").execute(segment_source(), config, run_id="segment_watch")
    assert result.status == "success"
    assert result.analysis["summary"]["watch_count"] > 0


def test_segment_merge_without_n_parameter_compiles_with_autodetect(tmp_path: Path) -> None:
    source = """
#include <bits/stdc++.h>
using namespace std;

void merge_node(vector<int>& seg, int v) {
    seg[v] = seg[v * 2] + seg[v * 2 + 1];
}

void update_impl(vector<int>& seg, int v, int l, int r, int pos, int value) {
    if (l == r) {
        seg[v] = value;
        return;
    }
    int mid = (l + r) / 2;
    if (pos <= mid) update_impl(seg, v * 2, l, mid, pos, value);
    else update_impl(seg, v * 2 + 1, mid + 1, r, pos, value);
    merge_node(seg, v);
}

void update(vector<int>& seg, int n, int pos, int value) {
    update_impl(seg, 1, 0, n - 1, pos, value);
}

int query_impl(vector<int>& seg, int v, int l, int r, int ql, int qr) {
    if (qr < l || r < ql) return 0;
    if (ql <= l && r <= qr) return seg[v];
    int mid = (l + r) / 2;
    return query_impl(seg, v * 2, l, mid, ql, qr)
         + query_impl(seg, v * 2 + 1, mid + 1, r, ql, qr);
}

int query(vector<int>& seg, int n, int l, int r) {
    return query_impl(seg, 1, 0, n - 1, l, r);
}

int main() {
    int n, q;
    cin >> n >> q;
    vector<int> seg(4 * n, 0);
    while (q--) {
        int type;
        cin >> type;
        if (type == 1) {
            int pos, value;
            cin >> pos >> value;
            update(seg, n, pos, value);
        } else {
            int l, r;
            cin >> l >> r;
            cout << query(seg, n, l, r) << "\\n";
        }
    }
    return 0;
}
""".strip()
    input_data = "8 3\n1 3 7\n1 5 4\n2 0 7\n"

    result = PipelineOrchestrator(tmp_path / "runs").execute(source, {"auto_detect": True}, input_data=input_data, run_id="segment_no_n")

    assert result.status == "success"
    assert result.run["stdout"].strip() == "11"
    instrumented = result.artifacts["instrumented"]
    assert Path(instrumented).read_text(encoding="utf-8").count('CP_TRACE_SCOPE("segment_merge", "seg", 0);') == 1


def test_global_one_based_segment_tree_end_to_end(tmp_path: Path) -> None:
    input_data = """8 5
1 2 3 4 5 6 7 8
2 1 8
1 3 10
2 1 4
1 6 4
2 5 8
"""
    result = PipelineOrchestrator(tmp_path / "runs").execute(
        GLOBAL_ONE_BASED_SEGMENT_SOURCE,
        {"auto_detect": True, "limits": {"timeout_seconds": 5}},
        input_data=input_data,
        run_id="global_one_based_segment",
    )

    assert result.status == "success"
    assert result.run["stdout"] == "36\n17\n24\n"
    effective_config = result.instrumentation["effective_config"]
    assert effective_config["target_arrays"][0]["index_base"] == 1
    assert [array["name"] for array in effective_config["target_arrays"][:2]] == ["seg", "a"]
    assert effective_config["target_arrays"][1]["role"] == "base_array"
    assert effective_config["tree_model"]["seg"]["base_array"] == "a"
    assert effective_config["detected"]["role_inference"] == "ast"
    assert effective_config["detected"]["node_variable"] == "id"
    assert effective_config["operations"][1]["param_roles"] == {"node": "id", "lo": "l", "hi": "r", "pos": "pos"}
    assert result.analysis["findings"] == []
    assert result.analysis["tree_timeline"]["nodes"][0]["range"] == [1, 8]
    assert result.analysis["tree_timeline"]["base_arrays"] == [{"array": "a", "source_tree": "seg", "index_base": 1}]
    assert all(node["array"] != "a" for node in result.analysis["tree_timeline"]["nodes"])
    final_base = result.analysis["tree_timeline"]["steps"][-1]["base_states"]
    assert final_base["base:a:1"]["value"] == "1"
    assert final_base["base:a:3"]["value"] == "3"
    assert final_base["base:a:8"]["value"] == "8"
    first_root_update = next(
        op
        for op in result.analysis["operations"]
        if op["kind"] == "segment_update" and op["expected_indices"] == [1, 2, 5, 10]
    )
    assert first_root_update["observed_indices"] == [10, 5, 2, 1]
    assert any(op["kind"] == "segment_update" for op in result.analysis["operations"])


def test_multiple_recursive_segment_trees_end_to_end(tmp_path: Path) -> None:
    source = """
#include <bits/stdc++.h>
using namespace std;

int n;
long long a[100], sumTree[400], maxTree[400];

void build_sum(int id, int l, int r) {
    if (l == r) {
        sumTree[id] = a[l];
        return;
    }
    int mid = (l + r) / 2;
    build_sum(id * 2, l, mid);
    build_sum(id * 2 + 1, mid + 1, r);
    sumTree[id] = sumTree[id * 2] + sumTree[id * 2 + 1];
}

void build_max(int id, int l, int r) {
    if (l == r) {
        maxTree[id] = a[l];
        return;
    }
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
    cout << sumTree[1] << " " << maxTree[1] << "\\n";
    return 0;
}
""".strip()
    result = PipelineOrchestrator(tmp_path / "runs").execute(
        source,
        {"auto_detect": True, "limits": {"timeout_seconds": 5}},
        input_data="4\n1 5 2 3\n",
        run_id="multi_segment",
    )

    assert result.status == "success"
    assert result.run["stdout"] == "11 5\n"
    config = result.instrumentation["effective_config"]
    assert {item["array"] for item in config["tree_instances"]} == {"sumTree", "maxTree"}
    timeline = result.analysis["tree_timeline"]
    assert {item["array"] for item in timeline["tree_instances"]} == {"sumTree", "maxTree"}
    assert {"sumTree", "maxTree"} <= {node["array"] for node in timeline["nodes"]}
    assert timeline["steps"][-1]["base_states"]["base:a:4"]["value"] == "3"


def test_global_vector_resize_segment_tree_end_to_end(tmp_path: Path) -> None:
    source = """
#include <bits/stdc++.h>
#include <unordered_map>
#define _CRT_SECURE_NO_WARNINGS
#pragma GCC optimize ("O3")
using namespace std;
#define int long long

int n;
vector<int>a, node;
int q;

void update(int idx, int l, int r, int index, int value) {
    if (l == r) {
        a[index] = value;
        node[idx] = value;
        return;
    }
    int mid = (l + r) / 2;
    if (index <= mid) {
        update(2 * idx, l, mid, index, value);
    } else {
        update(2 * idx + 1, mid + 1, r, index, value);
    }
    node[idx] = node[idx * 2] + node[idx * 2 + 1];
}

int get(int idx, int l, int r, int u, int v) {
    if (u > r || v < l) return 0;
    if (l >= u && r <= v) return node[idx];
    int mid = (l + r) / 2;
    int left = get(idx * 2, l, mid, u, v);
    int right = get(idx * 2 + 1, mid + 1, r, u, v);
    return left + right;
}

signed main() {
    int n, q;
    cin >> n >> q;
    a.resize(n + 1, 0);
    node.resize(4 * n + 5, 0);
    while (q--) {
        int type, u, v;
        cin >> type >> u >> v;
        if (type == 1) update(1, 1, n, u, v);
        else cout << get(1, 1, n, u, v) << endl;
    }
    return 0;
}
""".strip()
    result = PipelineOrchestrator(tmp_path / "runs").execute(
        source,
        {"auto_detect": True, "limits": {"timeout_seconds": 5}},
        input_data="5 5\n1 1 3\n1 3 7\n2 1 3\n1 2 4\n2 2 5\n",
        run_id="global_vector_resize_segment",
    )

    assert result.status == "success"
    assert result.run["stdout"] == "10\n11\n"
    config = result.instrumentation["effective_config"]
    assert [item["array"] for item in config["tree_instances"]] == ["node"]
    operations = {item["function_name"]: item for item in config["operations"]}
    assert operations["update"]["param_roles"] == {"node": "idx", "lo": "l", "hi": "r", "pos": "index"}
    assert operations["get"]["operation_type"] == "query"
    assert operations["get"]["param_roles"] == {"node": "idx", "lo": "l", "hi": "r", "ql": "u", "qr": "v"}
    assert not any(finding["code"] == "SEGMENT_INDEX_OUTSIDE_SYNTHETIC_TREE" for finding in result.analysis["findings"])
    nodes = {node["id"]: node for node in result.analysis["tree_timeline"]["nodes"]}
    assert nodes["cell:node:8"]["range"] == [1, 1]
    assert nodes["cell:node:9"]["range"] == [2, 2]


def test_struct_node_segment_tree_field_trace(tmp_path: Path) -> None:
    source = """
#include <bits/stdc++.h>
using namespace std;

struct Node {
    long long sum = 0;
};

int n;
long long a[100];
Node st[400];

void build(int id, int l, int r) {
    if (l == r) {
        st[id].sum = a[l];
        return;
    }
    int mid = (l + r) / 2;
    build(id * 2, l, mid);
    build(id * 2 + 1, mid + 1, r);
    st[id].sum = st[id * 2].sum + st[id * 2 + 1].sum;
}

int main() {
    cin >> n;
    for (int i = 1; i <= n; i++) cin >> a[i];
    build(1, 1, n);
    cout << st[1].sum << "\\n";
    return 0;
}
""".strip()
    result = PipelineOrchestrator(tmp_path / "runs").execute(
        source,
        {"auto_detect": True, "limits": {"timeout_seconds": 5}},
        input_data="4\n1 5 2 3\n",
        run_id="struct_segment",
    )

    assert result.status == "success"
    assert result.run["stdout"] == "11\n"
    config = result.instrumentation["effective_config"]
    assert config["tree_model"]["st"]["base_array"] == "a"
    assert {"array": "st.sum", "field": "sum", "role": "node_field"} in config["tree_model"]["st"]["node_fields"]
    final_state = result.analysis["tree_timeline"]["steps"][-1]["states"]["cell:st:1"]
    assert final_state["fields"]["sum"] == "11"


def test_struct_node_whole_object_assignment_without_stream_operator(tmp_path: Path) -> None:
    source = """
#include <bits/stdc++.h>
using namespace std;

struct Node {
    long long sum;
    int mn;
    int mx;
    Node(long long s = 0, int lo = INT_MAX, int hi = INT_MIN) : sum(s), mn(lo), mx(hi) {}
};

int n;
int a[100];
Node st[400];

Node mergeNode(Node leftNode, Node rightNode) {
    return Node(leftNode.sum + rightNode.sum, min(leftNode.mn, rightNode.mn), max(leftNode.mx, rightNode.mx));
}

void build(int id, int l, int r) {
    if (l == r) {
        st[id] = Node(a[l], a[l], a[l]);
        return;
    }
    int mid = (l + r) / 2;
    build(id * 2, l, mid);
    build(id * 2 + 1, mid + 1, r);
    st[id] = mergeNode(st[id * 2], st[id * 2 + 1]);
}

int main() {
    cin >> n;
    for (int i = 1; i <= n; i++) cin >> a[i];
    build(1, 1, n);
    cout << st[1].sum << " " << st[1].mn << " " << st[1].mx << "\\n";
    return 0;
}
""".strip()
    result = PipelineOrchestrator(tmp_path / "runs").execute(
        source,
        {"auto_detect": True, "limits": {"timeout_seconds": 5}},
        input_data="4\n1 5 2 3\n",
        run_id="struct_node_object_assignment",
    )

    assert result.status == "success"
    assert result.run["stdout"] == "11 1 5\n"
    config = result.instrumentation["effective_config"]
    assert config["detected"]["array"] == "st"
    assert config["tree_model"]["st"]["base_array"] == "a"
    assert config["tree_instances"][0]["base_array"] == "a"
    final_state = result.analysis["tree_timeline"]["steps"][-1]["states"]["cell:st:1"]
    assert final_state["fields"]["sum"] == "11"
    assert final_state["fields"]["mn"] == "1"
    assert final_state["fields"]["mx"] == "5"


def test_lazy_segment_tree_parallel_field_end_to_end(tmp_path: Path) -> None:
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
    result = PipelineOrchestrator(tmp_path / "runs").execute(
        source,
        {"auto_detect": True, "limits": {"timeout_seconds": 5}},
        input_data="8 6\n1 4 6 7\n1 0 7 1\n2 0 7\n1 2 5 2\n2 3 6\n2 4 4\n",
        run_id="lazy_segment",
    )

    assert result.status == "success"
    assert result.run["stdout"] == "29\n31\n10\n"
    config = result.instrumentation["effective_config"]
    assert {item["array"] for item in config["tree_instances"]} == {"seg"}
    assert {"array": "lazy", "field": "lazy", "role": "lazy_field"} in config["tree_model"]["seg"]["node_fields"]
    assert any(step["phase"] == "apply_lazy" for step in result.analysis["tree_timeline"]["steps"])


def test_segment_tree_wrapper_update_impl_exposes_recursive_path(tmp_path: Path) -> None:
    source = """
#include <bits/stdc++.h>
using namespace std;

void merge_node(vector<int>& seg, int n, int v) {
    seg[v] = seg[v * 2] + seg[v * 2 + 1];
}

void update_impl(vector<int>& seg, int n, int v, int l, int r, int pos, int value) {
    if (l == r) {
        seg[v] = value;
        return;
    }
    int mid = (l + r) / 2;
    if (pos <= mid) update_impl(seg, n, v * 2, l, mid, pos, value);
    else update_impl(seg, n, v * 2 + 1, mid + 1, r, pos, value);
    merge_node(seg, n, v);
}

void update(vector<int>& seg, int n, int pos, int value) {
    update_impl(seg, n, 1, 0, n - 1, pos, value);
}

int main() {
    int n = 8;
    vector<int> seg(4 * n, 0);
    update(seg, n, 3, 7);
    update(seg, n, 5, 4);
    cout << seg[1] << "\\n";
    return 0;
}
""".strip()

    result = PipelineOrchestrator(tmp_path / "runs").execute(source, {"auto_detect": True}, run_id="wrapper_update_impl")

    assert result.status == "success"
    assert result.run["stdout"] == "11\n"
    original_lines = source.splitlines()
    leaf_source_line = next(index for index, line in enumerate(original_lines, start=1) if "seg[v] = value" in line)
    merge_source_line = next(index for index, line in enumerate(original_lines, start=1) if "seg[v] = seg[v * 2]" in line)
    merge_node_source_line = next(index for index, line in enumerate(original_lines, start=1) if "void merge_node" in line)
    update_impl_source_line = next(index for index, line in enumerate(original_lines, start=1) if "void update_impl" in line)
    leaf_condition_line = next(index for index, line in enumerate(original_lines, start=1) if "if (l == r)" in line)
    branch_condition_line = next(index for index, line in enumerate(original_lines, start=1) if "if (pos <= mid)" in line)
    else_branch_line = next(index for index, line in enumerate(original_lines, start=1) if "else update_impl" in line)
    wrapper_call_line = next(index for index, line in enumerate(original_lines, start=1) if "update_impl(seg, n, 1" in line)
    assert result.analysis["source_files"]["original"] == source
    assert "CP_TRACE_" not in result.analysis["source_files"]["original"]
    assert result.analysis["source_mapping"]
    operations = {operation["function_name"]: operation for operation in result.instrumentation["effective_config"]["operations"]}
    assert operations["update_impl"]["param_roles"] == {"node": "v", "lo": "l", "hi": "r", "pos": "pos"}
    assert all(finding["severity"] == "info" for finding in result.analysis["findings"])

    steps = result.analysis["tree_timeline"]["steps"]
    first_path = ["cell:seg:1", "cell:seg:2", "cell:seg:5", "cell:seg:11"]
    second_path = ["cell:seg:1", "cell:seg:3", "cell:seg:6", "cell:seg:13"]
    assert any(step["phase"] == "descend" and step["active_nodes"] == first_path for step in steps)
    assert any(step["phase"] == "leaf_write" and step["active_nodes"] == first_path for step in steps)
    assert any(step["phase"] == "descend" and step["active_nodes"] == second_path for step in steps)
    assert any(step["phase"] == "leaf_write" and step["active_nodes"] == second_path for step in steps)
    leaf_condition_values = [
        step["mutation"].get("value")
        for step in steps
        if step["type"] == "line" and step["line"] == leaf_condition_line and step["mutation"]["kind"] == "condition"
    ]
    branch_condition_values = [
        step["mutation"].get("value")
        for step in steps
        if step["type"] == "line" and step["line"] == branch_condition_line and step["mutation"]["kind"] == "condition"
    ]
    assert "true" in leaf_condition_values
    assert {"true", "false"} <= set(branch_condition_values)
    else_step = next(
        step
        for step in steps
        if step["type"] == "line"
        and step["line"] == else_branch_line
        and step["mutation"]["kind"] == "else"
        and step["active_nodes"] == ["cell:seg:1", "cell:seg:2"]
    )
    right_child_begin = next(
        step
        for step in steps
        if step["type"] == "op_begin"
        and step["node_id"] == "cell:seg:5"
        and step["active_nodes"] == ["cell:seg:1", "cell:seg:2", "cell:seg:5"]
    )
    assert else_step["step"] < right_child_begin["step"]
    wrapper_call_step = next(step for step in steps if step["type"] == "line" and step["line"] == wrapper_call_line)
    first_impl_begin = next(
        step
        for step in steps
        if step["type"] == "op_begin"
        and step["node_id"] == "cell:seg:1"
        and step["line"] == update_impl_source_line
    )
    assert wrapper_call_step["step"] < first_impl_begin["step"]
    merge_left_read = next(
        step
        for step in steps
        if step["type"] == "access"
        and step["phase"] == "merge_return"
        and step["node_id"] == "cell:seg:10"
    )
    assert merge_left_read["active_nodes"] == ["cell:seg:1", "cell:seg:2", "cell:seg:5"]
    assert merge_left_read["line"] == merge_source_line
    assert merge_left_read["call_stack"][-1]["line"] == merge_node_source_line
    leaf_write = next(
        step
        for step in steps
        if step["type"] == "access"
        and step["phase"] == "leaf_write"
        and step["node_id"] == "cell:seg:11"
    )
    assert leaf_write["line"] == leaf_source_line
    assert leaf_write["call_stack"][-1]["line"] == update_impl_source_line

    merge_writes = [
        step["node_id"]
        for step in steps
        if step["type"] == "access"
        and step["phase"] == "merge_return"
        and step["mutation"].get("mode") == "write"
    ]
    assert merge_writes[:3] == ["cell:seg:5", "cell:seg:2", "cell:seg:1"]
    assert merge_writes[3:6] == ["cell:seg:6", "cell:seg:3", "cell:seg:1"]


def test_pipeline_compile_error_is_graceful(tmp_path: Path) -> None:
    config = {"target_arrays": [], "operations": []}
    result = PipelineOrchestrator(tmp_path / "runs").execute("int main(){ syntax error }", config, run_id="bad")
    assert result.status == "compile_error"
    assert result.errors
