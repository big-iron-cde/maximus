"""JSON Query engine wrapper for maximus.

Provides a thin layer over jsonquerylang to run declarative queries against
parsed piclone captures and format the results for humans or machines.
"""

from __future__ import annotations

import json
from typing import Any

from maximus.models import Capture, Cycle


def capture_to_json(capture: Capture) -> dict[str, Any]:
    """Convert a :class:`Capture` into a plain JSON-serialisable dict."""
    return {
        "cycles": [
            {"seq": c.seq, "addr": c.addr, "data": c.data, "rw": c.rw}
            for c in capture.cycles
        ],
        "result": (
            {
                "cmd": capture.result.cmd,
                "reason": capture.result.reason,
                "cycles": capture.result.cycles,
            }
            if capture.result
            else None
        ),
    }


def _fmt_cycle(c: dict[str, Any]) -> str:
    rw = "R" if c.get("rw") == 0 else "W"
    return f"seq={c['seq']}  addr={c['addr']}  data={c['data']}  rw={rw}"


def format_result(value: Any, fmt: str) -> str:
    """Format a jsonquery result for the requested output style.

    *fmt* must be ``"json"`` or ``"human"``.
    """
    if fmt == "json":
        return json.dumps(value, separators=(",", ":"))

    # human
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "(empty list)"
        # If every item is a cycle-like dict, print a table
        if all(isinstance(item, dict) and "seq" in item for item in value):
            return "\n".join(_fmt_cycle(item) for item in value)
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        if "seq" in value and "addr" in value and "data" in value:
            return _fmt_cycle(value)
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def run_query(capture: Capture, query: str | list[Any]) -> Any:
    """Run a jsonquery against *capture* and return the raw result."""
    import jsonquerylang

    data = capture_to_json(capture)
    return jsonquerylang.jsonquery(data, query)
