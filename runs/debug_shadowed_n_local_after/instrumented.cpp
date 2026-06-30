#include <iostream>
#include <vector>
#include <algorithm>
#include <cstring>
#include <cstdio>
#include <cmath>
#include <string>
#include <map>
#include <set>
#include <queue>
#include <stack>
#include <numeric>
#include <functional>
#include <cassert>
#include <unordered_map>
#include "trace.hpp"

#define _CRT_SECURE_NO_WARNINGS
#pragma GCC optimize ("O3")
using namespace std;
#define int long long
int n;
vector<int>a;
cp_trace::TrackedArray<int> node("node", 0, 0, "segment_tree", 1);
int q;
void update(int idx, int l, int r, int index, int value) {
    CP_TRACE_WATCH("idx", idx);
    CP_TRACE_SCOPE("segment_update", "node", n);
    CP_TRACE_PARAM("node", idx);
    CP_TRACE_PARAM("lo", l);
    CP_TRACE_PARAM("hi", r);
    CP_TRACE_PARAM("pos", index);

    if (CP_TRACE_COND(11, (l == r))) { a[index] = value; CP_TRACE_AT(node, idx) = value; return; }
    CP_TRACE_LINE(12, "statement");
    int mid = (l + r) / 2;
    CP_TRACE_WATCH("mid", mid);
    if (CP_TRACE_COND(13, (index <= mid))) update(2 * idx, l, mid, index, value);
    else { CP_TRACE_LINE(14, "else"); update(2 * idx + 1, mid + 1, r, index, value); }
    CP_TRACE_AT(node, idx) = CP_TRACE_AT(node, idx * 2) + CP_TRACE_AT(node, idx * 2 + 1);
}
int get(int idx, int l, int r, int u, int v) {
    CP_TRACE_WATCH("idx", idx);
    CP_TRACE_SCOPE("segment_query", "node", n);
    CP_TRACE_PARAM("node", idx);
    CP_TRACE_PARAM("lo", l);
    CP_TRACE_PARAM("hi", r);
    CP_TRACE_PARAM("ql", u);
    CP_TRACE_PARAM("qr", v);

    if (CP_TRACE_COND(18, (u > r || v < l))) return 0;
    if (CP_TRACE_COND(19, (l >= u && r <= v))) return CP_TRACE_AT(node, idx);
    CP_TRACE_LINE(20, "statement");
    int mid = (l + r) / 2;
    CP_TRACE_WATCH("mid", mid);
    CP_TRACE_LINE(21, "call");
    int left = get(idx * 2, l, mid, u, v);
    CP_TRACE_WATCH("idx", idx);
    CP_TRACE_WATCH("left", left);
    CP_TRACE_LINE(22, "call");
    int right = get(idx * 2 + 1, mid + 1, r, u, v);
    CP_TRACE_WATCH("idx", idx);
    CP_TRACE_WATCH("right", right);
    return left + right;
}
signed main() {
    CP_TRACE_LINE(26, "statement");
    int n, q; cin >> n >> q;
    CP_TRACE_LINE(27, "call");
    a.resize(n + 1, 0); node.resize(4 * n + 5, 0);
    while (CP_TRACE_COND(28, (q--))) { int type, u, v; cin >> type >> u >> v; if (type == 1) update(1, 1, n, u, v); else cout << get(1, 1, n, u, v) << endl; }
    return 0;
}