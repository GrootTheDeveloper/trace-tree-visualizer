from __future__ import annotations

from pathlib import Path

from prototype.evaluation.dataset import fenwick_config, fenwick_source, non_target_config, non_target_source
from prototype.instrumenter import InstrumentConfig, Instrumenter
from prototype.instrumenter.autodetect import detect_config


def test_instrumenter_replaces_bits_header_and_adds_trace_include(tmp_path: Path) -> None:
    source = tmp_path / "fenwick.cpp"
    source.write_text(fenwick_source(), encoding="utf-8")
    result = Instrumenter(InstrumentConfig.from_dict(fenwick_config())).instrument(source, tmp_path / "out.cpp")
    assert result.success
    text = (tmp_path / "out.cpp").read_text(encoding="utf-8")
    assert '#include "trace.hpp"' in text
    assert "#include <bits/stdc++.h>" not in text


def test_instrumenter_replaces_vector_with_tracked_array(tmp_path: Path) -> None:
    source = tmp_path / "fenwick.cpp"
    source.write_text(fenwick_source(), encoding="utf-8")
    result = Instrumenter(InstrumentConfig.from_dict(fenwick_config())).instrument(source, tmp_path / "out.cpp")
    assert result.success
    text = (tmp_path / "out.cpp").read_text(encoding="utf-8")
    assert "cp_trace::TrackedArray<int> bit" in text
    assert "cp_trace::TrackedArray<int>& bit" in text


def test_instrumenter_replaces_array_accesses(tmp_path: Path) -> None:
    source = tmp_path / "fenwick.cpp"
    source.write_text(fenwick_source(), encoding="utf-8")
    result = Instrumenter(InstrumentConfig.from_dict(fenwick_config())).instrument(source, tmp_path / "out.cpp")
    assert result.success
    text = (tmp_path / "out.cpp").read_text(encoding="utf-8")
    assert "CP_TRACE_AT(bit, i)" in text


def test_instrumenter_source_mapping_points_back_to_original_lines(tmp_path: Path) -> None:
    source_text = """
#include <bits/stdc++.h>
using namespace std;
void update(vector<int>& bit, int n, int i, int delta) {
    while (i <= n) {
        bit[i] += delta;
        i += i & -i;
    }
}
int main() { return 0; }
""".strip()
    source = tmp_path / "fenwick.cpp"
    source.write_text(source_text, encoding="utf-8")
    result = Instrumenter(InstrumentConfig.from_dict(detect_config(source_text))).instrument(source, tmp_path / "out.cpp")

    assert result.success
    text = (tmp_path / "out.cpp").read_text(encoding="utf-8")
    assert "__CP_TRACE_ORIG_LINE__" not in text
    original_line = next(index for index, line in enumerate(source_text.splitlines(), start=1) if "bit[i] += delta" in line)
    instrumented_line = next(index for index, line in enumerate(text.splitlines(), start=1) if "CP_TRACE_AT(bit, i) += delta" in line)
    mapping = {item.instrumented_line: item.original_line for item in result.source_mapping}
    assert mapping[instrumented_line] == original_line


def test_instrumenter_handles_multi_c_array_declaration(tmp_path: Path) -> None:
    source_text = """
#include <bits/stdc++.h>
using namespace std;
int n;
long long a[100005], seg[400020];
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
int main() { return 0; }
"""
    source = tmp_path / "multi.cpp"
    source.write_text(source_text, encoding="utf-8")
    result = Instrumenter(InstrumentConfig.from_dict(detect_config(source_text))).instrument(source, tmp_path / "out.cpp")

    assert result.success
    text = (tmp_path / "out.cpp").read_text(encoding="utf-8")
    assert "long long a[100005];" in text
    assert 'cp_trace::TrackedArray<long long> seg("seg", 400020' in text
    assert "CP_TRACE_AT(seg, 400020)" not in text


def test_instrumenter_can_mark_non_target_operation(tmp_path: Path) -> None:
    source = tmp_path / "array.cpp"
    source.write_text(non_target_source(), encoding="utf-8")
    result = Instrumenter(InstrumentConfig.from_dict(non_target_config())).instrument(source, tmp_path / "out.cpp")
    assert result.success
    assert "array_scan" in (tmp_path / "out.cpp").read_text(encoding="utf-8")
