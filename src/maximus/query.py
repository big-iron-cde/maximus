"""Query and filter piclone captures."""

from __future__ import annotations

from maximus.models import Capture, Cycle


def filter_cycles(
    capture: Capture,
    *,
    addr: str | None = None,
    data: str | None = None,
    rw: int | None = None,
    min_seq: int | None = None,
    max_seq: int | None = None,
) -> list[Cycle]:
    """Return cycles matching all supplied criteria.

    All string comparisons are case-insensitive after upper-casing.
    """
    results: list[Cycle] = []
    for cycle in capture.cycles:
        if addr is not None and cycle.addr != addr.upper():
            continue
        if data is not None and cycle.data != data.upper():
            continue
        if rw is not None and cycle.rw != rw:
            continue
        if min_seq is not None and cycle.seq < min_seq:
            continue
        if max_seq is not None and cycle.seq > max_seq:
            continue
        results.append(cycle)
    return results


def reads(capture: Capture) -> list[Cycle]:
    """All read cycles."""
    return [c for c in capture.cycles if c.is_read()]


def writes(capture: Capture) -> list[Cycle]:
    """All write cycles."""
    return [c for c in capture.cycles if c.is_write()]


def by_address(capture: Capture, addr: str) -> list[Cycle]:
    """All cycles targeting *addr* (case-insensitive)."""
    return [c for c in capture.cycles if c.addr == addr.upper()]
