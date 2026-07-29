"""CLI entry point for Maximus — piclone bus-capture processor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from maximus import __version__
from maximus.ci import emit_annotation, write_output, write_step_summary
from maximus.jsonquery_engine import format_result, run_query
from maximus.models import Capture
from maximus.parser import parse_file, parse_stdin
from maximus.query import filter_cycles
from maximus.asm_parser import parse_asm_file
from maximus.decode6502 import (
    cross_check,
    decode_linear,
    format_decode_result,
    reconstruct_rom,
    trace_control_flow,
)
from maximus.verify import VerifyResult, load_spec, verify


def _get_capture(args: argparse.Namespace) -> Capture:
    if getattr(args, "file", None):
        return parse_file(args.file)
    return parse_stdin()


def _fmt_cycle(cycle: object) -> str:
    from maximus.models import Cycle
    c = cycle
    assert isinstance(c, Cycle)
    rw = "R" if c.is_read() else "W"
    return f"seq={c.seq}  addr={c.addr}  data={c.data}  rw={rw}"


def cmd_parse(args: argparse.Namespace) -> int:
    capture = _get_capture(args)
    print(f"Cycles captured: {len(capture)}")
    if capture.result:
        r = capture.result
        print(f"Result: cmd={r.cmd} reason={r.reason} total_cycles={r.cycles}")
    for cycle in capture.cycles:
        print(_fmt_cycle(cycle))
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    capture = _get_capture(args)
    results = filter_cycles(
        capture,
        addr=args.addr,
        data=args.data,
        rw=args.rw,
        min_seq=args.min_seq,
        max_seq=args.max_seq,
    )
    for cycle in results:
        print(_fmt_cycle(cycle))
    return 0


def cmd_jsonquery(args: argparse.Namespace) -> int:
    capture = _get_capture(args)
    result = run_query(capture, args.expression)
    print(format_result(result, args.format))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    capture = _get_capture(args)
    data = capture_to_dict(capture)

    checks = _load_checks(args.spec)
    results: list[dict] = []
    all_pass = True

    for name, expression in checks:
        try:
            value = run_query(capture, expression)
            # A check passes if the result is truthy (non-empty, non-zero, True)
            passed = bool(value) if not isinstance(value, list) else len(value) > 0
        except Exception as exc:
            passed = False
            value = str(exc)

        if not passed:
            all_pass = False

        results.append({"name": name, "pass": passed, "value": value})

    output = {"pass": all_pass, "results": results}

    if args.format == "json":
        print(json.dumps(output, separators=(",", ":")))
    else:
        for item in results:
            icon = "✅" if item["pass"] else "❌"
            print(f"{icon} {item['name']}")
        status = "PASS" if all_pass else "FAIL"
        print(f"\n[{status}] {sum(1 for r in results if r['pass'])}/{len(results)} checks passed")

    # CI integration
    from maximus.verify import VerifyResult
    verify_result = VerifyResult(
        pass_=all_pass,
        matched=sum(1 for r in results if r["pass"]),
        total=len(results),
        failed_at=None if all_pass else next((i for i, r in enumerate(results) if not r["pass"]), None),
        message="All checks passed" if all_pass else "One or more checks failed",
    )
    write_step_summary(verify_result)
    emit_annotation(verify_result)
    write_output("maximus_result", output)

    return 0 if all_pass else 1


def cmd_decode(args: argparse.Namespace) -> int:
    capture = _get_capture(args)
    rom = reconstruct_rom(capture)
    result = decode_linear(rom, start_addr=args.start)

    # Optional source cross-check
    cross_result = None
    if getattr(args, "source", None):
        source_bytes = parse_asm_file(args.source)
        cross_result = cross_check(rom, source_bytes)

    if args.format == "json":
        data = result.to_dict()
        if args.trace:
            data["annotations"] = {
                addr: ann.to_dict()
                for addr, ann in trace_control_flow(result).items()
            }
        if cross_result is not None:
            data["cross_check"] = cross_result.to_dict()
        print(json.dumps(data, separators=(",", ":")))
    else:
        print(format_decode_result(result, trace=args.trace))
        if cross_result is not None:
            print("")
            if cross_result.valid:
                print(f"✅ Cross-check: {cross_result.matches} bytes match")
            else:
                print(f"❌ Cross-check failed ({cross_result.matches} matches)")
                if cross_result.mismatches:
                    print("  Mismatches:")
                    for m in cross_result.mismatches:
                        print(f"    {m['addr']}: expected {m['expected']}, captured {m['captured']}")
                if cross_result.missing:
                    print(f"  Missing in capture: {', '.join(cross_result.missing)}")
                if cross_result.extra:
                    print(f"  Extra in capture: {', '.join(cross_result.extra)}")

    valid = result.valid and (cross_result is None or cross_result.valid)
    return 0 if valid else 1


def cmd_verify(args: argparse.Namespace) -> int:
    capture = _get_capture(args)
    expectations = load_spec(args.spec)
    result = verify(capture, expectations)

    if args.json:
        print(json.dumps(result.to_dict()))
    else:
        status = "PASS" if result.pass_ else "FAIL"
        print(f"[{status}] {result.message} ({result.matched}/{result.total})")

    write_step_summary(result)
    emit_annotation(result)
    write_output("maximus_result", result.to_dict())

    return 0 if result.pass_ else 1


def _load_checks(path: str) -> list[tuple[str, str]]:
    """Load check definitions from a file.

    Each line: ``Name -> expression``
    Blank lines and lines starting with ``#`` are ignored.
    """
    checks: list[tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "->" not in line:
                continue
            name, expr = line.split("->", 1)
            checks.append((name.strip(), expr.strip()))
    return checks


def capture_to_dict(capture: Capture) -> dict:
    from maximus.jsonquery_engine import capture_to_json
    return capture_to_json(capture)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maximus",
        description="Piclone bus-capture processor: parse, query, verify, jsonquery, check.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # parse
    parse_p = subparsers.add_parser("parse", help="Parse NDJSON and print a summary")
    parse_p.add_argument("file", nargs="?", help="NDJSON capture file (default: stdin)")
    parse_p.set_defaults(func=cmd_parse)

    # query (legacy filter mode)
    query_p = subparsers.add_parser("query", help="Query/filter captured cycles")
    query_p.add_argument("file", nargs="?", help="NDJSON capture file (default: stdin)")
    query_p.add_argument("--addr", help="Filter by address (hex)")
    query_p.add_argument("--data", help="Filter by data byte (hex)")
    query_p.add_argument("--rw", type=int, choices=[0, 1], help="Filter by rw (0=read, 1=write)")
    query_p.add_argument("--min-seq", type=int, help="Minimum sequence number")
    query_p.add_argument("--max-seq", type=int, help="Maximum sequence number")
    query_p.set_defaults(func=cmd_query)

    # jsonquery
    jq_p = subparsers.add_parser("jsonquery", help="Run a jsonquery expression against the capture")
    jq_p.add_argument("expression", help="JSON Query expression (text or JSON)")
    jq_p.add_argument("file", nargs="?", help="NDJSON capture file (default: stdin)")
    jq_p.add_argument("--format", choices=["json", "human"], default="json", help="Output format")
    jq_p.set_defaults(func=cmd_jsonquery)

    # check
    check_p = subparsers.add_parser("check", help="Run multiple jsonquery assertions from a spec file")
    check_p.add_argument("file", nargs="?", help="NDJSON capture file (default: stdin)")
    check_p.add_argument("--spec", required=True, help="Check spec file (name -> expression per line)")
    check_p.add_argument("--format", choices=["json", "human"], default="json", help="Output format")
    check_p.set_defaults(func=cmd_check)

    # decode
    decode_p = subparsers.add_parser("decode", help="Decode the 6502 instruction stream from the capture")
    decode_p.add_argument("file", nargs="?", help="NDJSON capture file (default: stdin)")
    decode_p.add_argument("--start", type=lambda s: int(s, 16), help="Override start address (hex)")
    decode_p.add_argument("--format", choices=["json", "human"], default="json", help="Output format")
    decode_p.add_argument("--trace", action="store_true", help="Annotate control flow (branches, jumps, targets)")
    decode_p.add_argument("--source", help="Source assembly file (.s) to cross-check against")
    decode_p.set_defaults(func=cmd_decode)

    # verify
    verify_p = subparsers.add_parser("verify", help="Verify capture against a YAML/JSON spec")
    verify_p.add_argument("file", nargs="?", help="NDJSON capture file (default: stdin)")
    verify_p.add_argument("--spec", required=True, help="YAML/JSON verification spec")
    verify_p.add_argument("--json", action="store_true", help="Output result as JSON")
    verify_p.set_defaults(func=cmd_verify)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
