#include <bits/stdc++.h>
using namespace std;

// Recursive Segment Tree with Lazy Propagation — range add, range sum query

const int MAXN = 100005;
int seg[4 * MAXN];
int lazy[4 * MAXN];
int n;

void push_down(int v, int l, int r) {
    if (lazy[v] != 0) {
        int mid = (l + r) / 2;
        seg[2 * v]     += lazy[v] * (mid - l + 1);
        lazy[2 * v]    += lazy[v];
        seg[2 * v + 1] += lazy[v] * (r - mid);
        lazy[2 * v + 1] += lazy[v];
        lazy[v] = 0;
    }
}

void build(int v, int l, int r, int* arr) {
    lazy[v] = 0;
    if (l == r) {
        seg[v] = arr[l];
        return;
    }
    int mid = (l + r) / 2;
    build(2 * v, l, mid, arr);
    build(2 * v + 1, mid + 1, r, arr);
    seg[v] = seg[2 * v] + seg[2 * v + 1];
}

void range_add(int v, int l, int r, int ql, int qr, int val) {
    if (ql > r || qr < l) return;
    if (ql <= l && r <= qr) {
        seg[v]  += val * (r - l + 1);
        lazy[v] += val;
        return;
    }
    push_down(v, l, r);
    int mid = (l + r) / 2;
    range_add(2 * v, l, mid, ql, qr, val);
    range_add(2 * v + 1, mid + 1, r, ql, qr, val);
    seg[v] = seg[2 * v] + seg[2 * v + 1];
}

int range_sum(int v, int l, int r, int ql, int qr) {
    if (ql > r || qr < l) return 0;
    if (ql <= l && r <= qr) return seg[v];
    push_down(v, l, r);
    int mid = (l + r) / 2;
    return range_sum(2 * v, l, mid, ql, qr)
         + range_sum(2 * v + 1, mid + 1, r, ql, qr);
}

int main() {
    n = 6;
    int arr[7] = {0, 1, 2, 3, 4, 5, 6};  // 1-indexed
    build(1, 1, n, arr);
    cout << range_sum(1, 1, n, 2, 5) << "\n";  // expected: 2+3+4+5 = 14
    range_add(1, 1, n, 1, 4, 10);
    cout << range_sum(1, 1, n, 2, 5) << "\n";  // expected: 12+13+14+15 = 54... no: 2+10=12, 3+10=13, 4+10=14, 5=5 → 12+13+14+5=44
    return 0;
}
