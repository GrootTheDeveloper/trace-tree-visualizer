#include <bits/stdc++.h>
using namespace std;

// Iterative Segment Tree (bottom-up) — sum queries, point updates
// Node i has children 2*i and 2*i+1; leaves at positions [n, 2n-1]

int n;
vector<int> seg;

void build(vector<int>& arr) {
    for (int i = 0; i < n; i++)
        seg[n + i] = arr[i];
    for (int i = n - 1; i >= 1; i--)
        seg[i] = seg[2 * i] + seg[2 * i + 1];
}

void update(int pos, int val) {
    pos += n;
    seg[pos] = val;
    for (pos >>= 1; pos >= 1; pos >>= 1)
        seg[pos] = seg[2 * pos] + seg[2 * pos + 1];
}

int query(int l, int r) {
    int res = 0;
    for (l += n, r += n + 1; l < r; l >>= 1, r >>= 1) {
        if (l & 1) res += seg[l++];
        if (r & 1) res += seg[--r];
    }
    return res;
}

int main() {
    n = 8;
    seg.assign(2 * n, 0);
    vector<int> arr = {0, 1, 2, 3, 4, 5, 6, 7};
    build(arr);
    cout << query(1, 5) << "\n";  // expected: 1+2+3+4+5 = 15
    update(3, 10);
    cout << query(1, 5) << "\n";  // expected: 1+2+10+4+5 = 22
    return 0;
}
