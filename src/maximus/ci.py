"""CI / workflow output helpers for maximus.

When running inside GitHub Actions these helpers emit step summaries and
annotations that show up in the workflow UI.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from maximus.verify import VerifyResult


def is_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def write_step_summary(result: VerifyResult) -> None:
    """Append a markdown summary to ``$GITHUB_STEP_SUMMARY`` if available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    status = "✅ PASS" if result.pass_ else "❌ FAIL"
    lines = [
        "## Maximus Verification Result\n",
        f"**Status:** {status}\n",
        f"- Matched: {result.matched} / {result.total}\n",
    ]
    if result.failed_at is not None:
        lines.append(f"- Failed at expectation: {result.failed_at + 1}\n")
    lines.append(f"\n{result.message}\n")

    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.writelines(lines)


def emit_annotation(result: VerifyResult) -> None:
    """Emit a GitHub Actions workflow annotation on failure."""
    if result.pass_:
        return
    message = result.message.replace("\n", "%0A")
    # Using the special ::error:: syntax for GHA
    print(f"::error title=Maximus Verification Failed::{message}", file=sys.stderr)


def write_output(name: str, value: dict) -> None:
    """Write a JSON object to a GitHub Actions output parameter."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={json.dumps(value)}\n")
