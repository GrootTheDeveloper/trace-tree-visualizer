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
    if (l == r) { a[index] = value; node[idx] = value; return; }
    int mid = (l + r) / 2;
    if (index <= mid) update(2 * idx, l, mid, index, value);
    else update(2 * idx + 1, mid + 1, r, index, value);
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
    int n, q; cin >> n >> q;
    a.resize(n + 1, 0); node.resize(4 * n + 5, 0);
    while (q--) { int type, u, v; cin >> type >> u >> v; if (type == 1) update(1, 1, n, u, v); else cout << get(1, 1, n, u, v) << endl; }
    return 0;
}
