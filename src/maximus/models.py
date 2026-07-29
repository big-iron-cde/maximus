"""Dataclasses for piclone bus-cycle captures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Cycle:
    """A single bus cycle from a piclone capture."""

    seq: int
    addr: str
    data: str
    rw: Literal[0, 1]

    def is_read(self) -> bool:
        return self.rw == 0

    def is_write(self) -> bool:
        return self.rw == 1


@dataclass(frozen=True)
class CaptureResult:
    """The final result event from a piclone capture."""

    cmd: str
    reason: str
    cycles: int


@dataclass
class Capture:
    """A complete piclone bus capture."""

    cycles: list[Cycle]
    result: CaptureResult | None = None

    def __len__(self) -> int:
        return len(self.cycles)
