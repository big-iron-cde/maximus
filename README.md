# Maximus

A Python CLI tool that **processes, queries, and verifies** [piclone](https://github.com/big-iron-cde/piclone) bus-capture output.

Piclone is a Raspberry Pi Pico firmware that emulates ROM and clocks a W65C02S CPU. Its `hardware capture` command streams NDJSON bus cycles over USB-serial. **Maximus** turns that raw output into structured, testable results.

Built with [uv](https://docs.astral.sh/uv/).

---

## Features

- **Parse** raw piclone NDJSON into a clean cycle summary.
- **Query** captures with filters (`--addr`, `--data`, `--rw`, `--min-seq`, `--max-seq`).
- **JSON Query** — run declarative [jsonquerylang](https://jsonquerylang.org/) expressions directly against the capture.
- **Check** — run multiple jsonquery assertions from a spec file and get a single pass/fail result.
- **Verify** (legacy) — verify captures against a YAML/JSON expectation list.
- **CI-native** — automatically writes GitHub Actions step summaries, annotations, and workflow outputs when running inside GHA.

---

## Installation

```bash
uv sync
```

---

## Usage

### Parse a capture

```bash
uv run maximus parse capture.jsonl
```

Prints a human-readable summary of every bus cycle.

### Query a capture (legacy filter mode)

```bash
# Show only writes to address 0200
uv run maximus query capture.jsonl --addr 0200 --rw 1

# Show all reads
uv run maximus query capture.jsonl --rw 0
```

### JSON Query

Run a [jsonquerylang](https://jsonquerylang.org/) expression against the capture data. The capture is exposed as a JSON object with `.cycles` (list) and `.result` (object).

```bash
# Get the stop reason
uv run maximus jsonquery '.result.reason' capture.jsonl
# -> "stp"

# Count cycles
uv run maximus jsonquery '.cycles | size()' capture.jsonl
# -> 39

# Find all writes to 0200
uv run maximus jsonquery '.cycles | filter(.addr == "0200" and .rw == 1)' capture.jsonl --format human
# -> seq=26  addr=0200  data=00  rw=W
# -> seq=34  addr=0200  data=00  rw=W
```

Default output is JSON. Use `--format human` for readable tables.

### Check (multi-assertion verification)

Write a plain-text spec file where each line is `Name -> jsonquery expression`:

```text
# checks.txt
Ends with STP              -> .result.reason == "stp"
Exactly 39 cycles          -> .cycles | size() == 39
Write to 0200 exists       -> .cycles | filter(.addr == "0200" and .rw == 1) | size() > 0
Program starts at 8000     -> .cycles | filter(.addr == "8000") | size() > 0
```

Run it:

```bash
uv run maximus check capture.jsonl --spec checks.txt
```

Default JSON output:
```json
{"pass":true,"results":[{"name":"Ends with STP","pass":true,"value":true},...]}
```

Human-readable output:
```bash
uv run maximus check capture.jsonl --spec checks.txt --format human
```
```
✅ Ends with STP
✅ Exactly 39 cycles
✅ Write to 0200 exists
✅ Program starts at 8000

[PASS] 4/4 checks passed
```

Exit codes:
- `0` → all checks passed
- `1` → one or more checks failed

### Pipe from Romulan

Since Romulan outputs NDJSON to stdout, you can pipe directly into Maximus:

```bash
uv run romulan hardware capture --max-cycles 500 | uv run maximus jsonquery '.result.reason'
uv run romulan hardware capture --max-cycles 500 | uv run maximus check --spec checks.txt --format human
```

### Decode instruction stream

Reconstruct the 6502/65C02 instruction stream from captured ROM cycles. Validates opcode bytes, operand counts, and detects undefined opcodes or truncated instructions.

```bash
# Human-readable disassembly
uv run maximus decode capture.jsonl --format human
```

Output:
```
Reset vector: $8000
8000: D8       CLD
8001: 18       CLC
8002: A9 05    LDA #$05
8004: 18       CLC
8005: 69 0A    ADC #$0A
...
8016: DB       STP
```

JSON output (default, for workflows):
```bash
uv run maximus decode capture.jsonl
# -> {"instructions":[{"addr":"8000","bytes":["D8"],"mnemonic":"CLD","mode":"imp","length":1,"valid":true},...],"reset_vector":"8000","valid":true,"errors":[]}
```

Override start address:
```bash
uv run maximus decode capture.jsonl --start 8002 --format human
```

### Decode with control-flow trace

Add `--trace` to annotate branches, jumps, jump-targets, and unreachable code:

```bash
uv run maximus decode capture.jsonl --format human --trace
```

Example output for a program with branches:
```
Reset vector: $8000
8000: A9 00    LDA #$00
8002: F0 02    BEQ $8006 → 8006 *
8004: A9 01    LDA #$01
8006: D0 FA    BNE $8002 → 8002 *
8008: DB       STP
```

Annotations:
- `→ 8006` — computed branch/jump target address
- `*` — this instruction is the target of a branch or jump
- `[unreachable]` — no execution path reaches this instruction (e.g., code after `STP` with no jumps to it)

JSON output with trace metadata:
```bash
uv run maximus decode capture.jsonl --trace
# -> includes "annotations":{"8002":{"flow_type":"branch","target_addr":"8006","is_target":false},...}
```

### Source cross-check (`--source demo.s`)

Compare the captured bytes against a 6502 assembly source file to catch mismatches:

```bash
uv run maximus decode capture.jsonl --source demo.s --format human
```

Output:
```
Reset vector: $8000
8000: D8       CLD
...
8016: DB       STP

✅ Cross-check: 25 bytes match
```

On mismatch:
```
❌ Cross-check failed (24 matches)
  Mismatches:
    8003: expected 05, captured 03
  Missing in capture: 8017
  Extra in capture: FFFF
```

JSON output includes the cross-check block:
```bash
uv run maximus decode capture.jsonl --source demo.s
# -> {"instructions":[...],"cross_check":{"matches":25,"mismatches":[],"missing":[],"extra":[],"valid":true}}
```

### Verify against a spec (legacy YAML mode)

Create a spec file (YAML or JSON):

```yaml
# test_spec.yaml
expect:
  - addr: "8000"
    data: "D8"
    rw: 0
    label: "reset_vector"
  - addr: "8001"
    data: "18"
    rw: 0
    label: "CLC"
  - addr: "0200"
    data: "02"
    rw: 1
    label: "STA result"
```

Run verification:

```bash
uv run maximus verify capture.jsonl --spec test_spec.yaml
```

Exit codes:
- `0` → all expectations matched
- `1` → at least one expectation failed

Get machine-readable JSON output:

```bash
uv run maximus verify capture.jsonl --spec test_spec.yaml --json
# {"pass": true, "matched": 3, "total": 3, "failed_at": null, "message": "All expectations matched"}
```

---

## CI / Workflow Integration

When `GITHUB_ACTIONS=true` is set in the environment, `maximus check`, `maximus verify`, and `maximus decode` automatically:

1. Append a markdown summary to the job step summary.
2. Emit a `::error::` annotation on failure.
3. Write the JSON result to the `maximus_result` output variable for downstream steps.

Example workflow step:

```yaml
- name: Verify piclone capture
  run: |
    romulan hardware capture --until stp --port /dev/ttyACM0 | uv run maximus check --spec specs/addition.txt --json
  id: verify

- name: Fail on verification error
  if: ${{ fromJson(steps.verify.outputs.maximus_result).pass == false }}
  run: echo "Verification failed!"
```

---

## Project Structure

```
maximus/
├── src/maximus/
│   ├── __init__.py          # Package version
│   ├── cli.py               # argparse CLI (parse, query, jsonquery, check, decode, verify)
│   ├── models.py            # Cycle, Capture, CaptureResult dataclasses
│   ├── parser.py            # NDJSON ingestion
│   ├── query.py             # Filtering / exploration
│   ├── verify.py            # Assertion engine + spec loader (legacy)
│   ├── jsonquery_engine.py  # jsonquerylang wrapper + formatting
│   ├── decode6502.py        # 6502/65C02 opcode metadata + linear decoder
│   ├── asm_parser.py        # Loose 6502 assembly parser for source cross-check
│   └── ci.py                # GitHub Actions output helpers
├── tests/
│   ├── test_cli.py
│   ├── test_cli_jsonquery.py
│   ├── test_parser.py
│   ├── test_query.py
│   ├── test_verify.py
│   ├── test_jsonquery_engine.py
│   ├── test_decode.py
│   ├── test_decode_trace.py
│   └── test_asm_parser.py
├── pyproject.toml
└── README.md
```

---

## License

MIT
