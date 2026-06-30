from __future__ import annotations

from typing import Iterable

from .model import Access


def as_int(value: str | int | None, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def lowbit(value: int) -> int:
    return value & -value


def compact_indices(accesses: Iterable[Access], mode: str | None = None) -> list[int]:
    indices: list[int] = []
    for access in accesses:
        if mode is not None and access.mode != mode:
            continue
        if not indices or indices[-1] != access.index:
            indices.append(access.index)
    return indices


def is_subsequence(expected: list[int], observed: list[int]) -> bool:
    pos = 0
    for item in observed:
        while pos < len(expected) and expected[pos] != item:
            pos += 1
        if pos == len(expected):
            return False
        pos += 1
    return True

