"""Parse piclone NDJSON capture output."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from maximus.models import Capture, CaptureResult, Cycle


def _parse_cycle(data: dict) -> Cycle:
    """Parse a single cycle dict into a Cycle dataclass."""
    return Cycle(
        seq=int(data["seq"]),
        addr=str(data["addr"]).upper(),
        data=str(data["data"]).upper(),
        rw=int(data["rw"]),  # type: ignore[arg-type]
    )


def parse_line(line: str) -> Cycle | CaptureResult | None:
    """Parse one NDJSON line.

    Returns a :class:`Cycle`, :class:`CaptureResult`, or ``None`` for
    unrelated lines (e.g. monitor events without a ``data`` block).
    """
    line = line.strip()
    if not line:
        return None

    obj = json.loads(line)
    if obj.get("type") == "event" and obj.get("event") == "cycle":
        return _parse_cycle(obj["data"])
    if obj.get("type") == "result":
        return CaptureResult(
            cmd=str(obj["cmd"]),
            reason=str(obj["data"]["reason"]),
            cycles=int(obj["data"]["cycles"]),
        )
    return None


def parse_stream(stream: TextIO) -> Capture:
    """Parse an entire NDJSON stream into a :class:`Capture`."""
    cycles: list[Cycle] = []
    result: CaptureResult | None = None

    for line in stream:
        parsed = parse_line(line)
        if isinstance(parsed, Cycle):
            cycles.append(parsed)
        elif isinstance(parsed, CaptureResult):
            result = parsed

    return Capture(cycles=cycles, result=result)


def parse_file(path: str | Path) -> Capture:
    """Parse a file containing NDJSON piclone output."""
    with open(path, "r", encoding="utf-8") as fh:
        return parse_stream(fh)


def parse_stdin() -> Capture:
    """Parse NDJSON piclone output from ``stdin``."""
    return parse_stream(sys.stdin)
