from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from prototype.analyzer import analyze_trace


def write_trace(events: list[dict]) -> Path:
    temp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".jsonl")
    with temp:
        for event in events:
            temp.write(json.dumps(event) + "\n")
    return Path(temp.name)


class AnalyzerTests(unittest.TestCase):
    def test_fenwick_update_matches_lowbit_sequence(self) -> None:
        path = write_trace(
            [
                {"event": "array", "seq": 1, "array": "bit", "size": 9, "structure": "fenwick", "index_base": 1},
                {"event": "op_begin", "seq": 2, "op_id": 1, "kind": "fenwick_update", "array": "bit", "n": 8},
                {"event": "op_param", "seq": 3, "op_id": 1, "key": "pos", "value": "3"},
                {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "bit", "index": 3},
                {"event": "access", "seq": 5, "op_id": 1, "mode": "write", "array": "bit", "index": 4},
                {"event": "access", "seq": 6, "op_id": 1, "mode": "write", "array": "bit", "index": 8},
            ]
        )
        result = analyze_trace(path)
        self.assertEqual(result.operations[0].status, "recognized")
        self.assertEqual(result.operations[0].expected_indices, [3, 4, 8])

    def test_fenwick_update_reports_bad_sequence(self) -> None:
        path = write_trace(
            [
                {"event": "op_begin", "seq": 1, "op_id": 1, "kind": "fenwick_update", "array": "bit", "n": 8},
                {"event": "op_param", "seq": 2, "op_id": 1, "key": "pos", "value": "3"},
                {"event": "access", "seq": 3, "op_id": 1, "mode": "write", "array": "bit", "index": 3, "file": "a.cpp", "line": 5},
                {"event": "access", "seq": 4, "op_id": 1, "mode": "write", "array": "bit", "index": 5, "file": "a.cpp", "line": 5},
            ]
        )
        result = analyze_trace(path)
        self.assertEqual(result.operations[0].status, "mismatch")
        self.assertEqual(result.operations[0].findings[0].code, "FENWICK_BAD_INDEX_SEQUENCE")
        self.assertEqual(result.operations[0].findings[0].suspect_lines[0], "a.cpp:5")
        self.assertIn("slice", result.operations[0].findings[0].evidence)

    def test_segment_merge_reports_duplicate_child(self) -> None:
        path = write_trace(
            [
                {"event": "op_begin", "seq": 1, "op_id": 1, "kind": "segment_merge", "array": "seg", "n": 8},
                {"event": "op_param", "seq": 2, "op_id": 1, "key": "v", "value": "2"},
                {"event": "access", "seq": 3, "op_id": 1, "mode": "read", "array": "seg", "index": 4, "file": "seg.cpp", "line": 5},
                {"event": "access", "seq": 4, "op_id": 1, "mode": "read", "array": "seg", "index": 4, "file": "seg.cpp", "line": 5},
                {"event": "access", "seq": 5, "op_id": 1, "mode": "write", "array": "seg", "index": 2, "file": "seg.cpp", "line": 5},
            ]
        )
        result = analyze_trace(path)
        self.assertEqual(result.operations[0].findings[0].code, "SEGMENT_BAD_MERGE_CHILDREN")
        self.assertEqual(result.operations[0].findings[0].suspect_lines[0], "seg.cpp:5")


if __name__ == "__main__":
    unittest.main()
