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
const int oo = 1e9 + 7;
const int MOD = 1e9 + 7;
const int MAXN = 1e6;
const int MAX = 2e5;
int dx[4] = { 0, 0, 1, -1 };
int dy[4] = { 1, -1, 0 ,0 };
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

    if (CP_TRACE_COND(17, (l == r))) { a[index] = value; CP_TRACE_AT(node, idx) = value; return; }
    CP_TRACE_LINE(18, "statement");
    int mid = (l + r) / 2;
    CP_TRACE_WATCH("mid", mid);
    if (CP_TRACE_COND(19, (index <= mid))) update(2 * idx, l, mid, index, value);
    else { CP_TRACE_LINE(20, "else"); update(2 * idx + 1, mid + 1, r, index, value); }
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

    if (CP_TRACE_COND(24, (u > r || v < l))) return 0;
    if (CP_TRACE_COND(25, (l >= u && r <= v))) return CP_TRACE_AT(node, idx);
    CP_TRACE_LINE(26, "statement");
    int mid = (l + r) / 2;
    CP_TRACE_WATCH("mid", mid);
    CP_TRACE_LINE(27, "call");
    int left = get(idx * 2, l, mid, u, v);
    CP_TRACE_WATCH("idx", idx);
    CP_TRACE_WATCH("left", left);
    CP_TRACE_LINE(28, "call");
    int right = get(idx * 2 + 1, mid + 1, r, u, v);
    CP_TRACE_WATCH("idx", idx);
    CP_TRACE_WATCH("right", right);
    return left + right;
}
signed main() {
    CP_TRACE_LINE(32, "statement");
    int n, q; cin >> n >> q;
    CP_TRACE_LINE(33, "call");
    a.resize(n + 1, 0); node.resize(4 * n + 5, 0);
    while (CP_TRACE_COND(34, (q--))) { int type, u, v; cin >> type >> u >> v; if (type == 1) update(1, 1, n, u, v); else cout << get(1, 1, n, u, v) << endl; }
    return 0;
}