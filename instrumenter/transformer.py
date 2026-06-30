from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transform:
    start: int
    end: int
    replacement: str


class SourceTransformer:
    def apply_transformations(self, source: str, transforms: list[Transform]) -> str:
        result = source
        for transform in sorted(transforms, key=lambda item: item.start, reverse=True):
            result = result[: transform.start] + transform.replacement + result[transform.end :]
        return result

