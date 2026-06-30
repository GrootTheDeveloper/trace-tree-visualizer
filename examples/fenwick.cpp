#include <iostream>

#include "../cpp/trace.hpp"

using cp_trace::TrackedArray;

int lowbit(int x) {
    return x & -x;
}

void add(TrackedArray<int>& bit, int n, int pos, int delta) {
    CP_TRACE_SCOPE("fenwick_update", "bit", n);
    CP_TRACE_PARAM("pos", pos);
    CP_TRACE_PARAM("delta", delta);
    for (int i = pos; i <= n; i += lowbit(i)) {
        CP_TRACE_AT(bit, i) += delta;
    }
}

int sum(TrackedArray<int>& bit, int pos) {
    CP_TRACE_SCOPE("fenwick_query", "bit", pos);
    CP_TRACE_PARAM("pos", pos);
    int ans = 0;
    for (int i = pos; i > 0; i -= lowbit(i)) {
        ans += CP_TRACE_AT(bit, i);
    }
    return ans;
}

int main() {
    CP_TRACE_OPEN("fenwick_trace.jsonl");
    TrackedArray<int> bit("bit", 9, 0, "fenwick", 1);
    add(bit, 8, 3, 5);
    add(bit, 8, 4, 2);
    std::cout << sum(bit, 7) << "\n";
    CP_TRACE_CLOSE();
    return 0;
}

