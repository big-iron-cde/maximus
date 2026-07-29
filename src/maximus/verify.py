"""Verify piclone captures against expected behaviour specs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from maximus.models import Capture, Cycle


@dataclass(frozen=True)
class Expectation:
    """One expected event in the capture."""

    addr: str
    data: str | None = None
    rw: Literal[0, 1] | None = None
    label: str | None = None


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of verifying a capture against a spec."""

    pass_: bool
    matched: int
    total: int
    failed_at: int | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass": self.pass_,
            "matched": self.matched,
            "total": self.total,
            "failed_at": self.failed_at,
            "message": self.message,
        }


def _match(cycle: Cycle, expectation: Expectation) -> bool:
    if cycle.addr != expectation.addr.upper():
        return False
    if expectation.data is not None and cycle.data != expectation.data.upper():
        return False
    if expectation.rw is not None and cycle.rw != expectation.rw:
        return False
    return True


def verify(capture: Capture, expectations: list[Expectation]) -> VerifyResult:
    """Check that every expectation is satisfied in order.

    The search is greedy: after matching expectation *i* we continue
    scanning from the next cycle, so unrelated intermediate cycles are
    tolerated.
    """
    cycle_idx = 0
    matched = 0

    for exp_idx, exp in enumerate(expectations):
        found = False
        while cycle_idx < len(capture.cycles):
            if _match(capture.cycles[cycle_idx], exp):
                found = True
                cycle_idx += 1
                matched += 1
                break
            cycle_idx += 1

        if not found:
            label = f" ({exp.label})" if exp.label else ""
            return VerifyResult(
                pass_=False,
                matched=matched,
                total=len(expectations),
                failed_at=exp_idx,
                message=f"Expectation {exp_idx + 1}{label} not found: addr={exp.addr}, data={exp.data}, rw={exp.rw}",
            )

    return VerifyResult(
        pass_=True,
        matched=matched,
        total=len(expectations),
        message="All expectations matched",
    )


def load_spec(path: str | Path) -> list[Expectation]:
    """Load a YAML or JSON verification spec."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    expectations: list[Expectation] = []
    for item in raw.get("expect", []):
        rw = item.get("rw")
        if rw is not None:
            rw = int(rw)  # type: ignore[assignment]
        expectations.append(
            Expectation(
                addr=str(item["addr"]),
                data=item.get("data"),
                rw=rw,  # type: ignore[arg-type]
                label=item.get("label"),
            )
        )
    return expectations
