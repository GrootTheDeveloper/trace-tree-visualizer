#include <iostream>

#include "../cpp/trace.hpp"

using cp_trace::TrackedArray;

void update_impl(TrackedArray<int>& tree, int v, int left, int right, int pos, int value) {
    if (left == right) {
        CP_TRACE_AT(tree, v) = value;
        return;
    }
    int mid = (left + right) / 2;
    if (pos <= mid) {
        update_impl(tree, v * 2, left, mid, pos, value);
    } else {
        update_impl(tree, v * 2 + 1, mid + 1, right, pos, value);
    }
    CP_TRACE_AT(tree, v) = CP_TRACE_AT(tree, v * 2) + CP_TRACE_AT(tree, v * 2 + 1);
}

void update_root(TrackedArray<int>& tree, int n, int pos, int value) {
    CP_TRACE_SCOPE("segment_update", "seg", n);
    CP_TRACE_PARAM("pos", pos);
    CP_TRACE_PARAM("root", 1);
    update_impl(tree, 1, 0, n - 1, pos, value);
}

int main() {
    CP_TRACE_OPEN("segment_trace.jsonl");
    TrackedArray<int> seg("seg", 32, 0, "segment_tree", 0);
    update_root(seg, 8, 3, 7);
    update_root(seg, 8, 5, 4);
    std::cout << "done\n";
    CP_TRACE_CLOSE();
    return 0;
}
