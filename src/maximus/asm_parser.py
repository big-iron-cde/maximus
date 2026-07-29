"""Loose 6502/65C02 assembly parser for source cross-check.

Reads a ``.s`` file and produces a mapping ``address -> [expected_bytes]``.
This is *not* a full two-pass assembler — it handles the subset used in
simple test programs and is intentionally lightweight and standalone.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from maximus.decode6502 import (
    _ABS,
    _ABSX,
    _ABSY,
    _ACC,
    _IMM,
    _IND,
    _IZP,
    _IZX,
    _IZY,
    _OPCODES,
    _REL,
    _ZP,
    _ZPX,
    _ZPY,
)


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

def _parse_number(token: str) -> int | None:
    """Parse ``$hex``, ``0xhex``, or decimal."""
    try:
        if token.startswith("$"):
            return int(token[1:], 16)
        if token.lower().startswith("0x"):
            return int(token, 16)
        if token.isdigit() or (token.startswith("-") and token[1:].isdigit()):
            return int(token, 10)
    except ValueError:
        pass
    return None


def _tokenise(line: str) -> list[str]:
    """Split a line into tokens, dropping comments."""
    if ";" in line:
        line = line.split(";", 1)[0]
    line = line.replace(",", " ")
    return line.strip().split()


# ---------------------------------------------------------------------------
# Assembler helpers (loose)
# ---------------------------------------------------------------------------

def _resolve_mode(mnemonic: str, tokens: list[str]) -> str:
    """Determine addressing mode from operand tokens."""
    if not tokens:
        modes = _OPCODES.get(mnemonic, {})
        if "imp" in modes:
            return "imp"
        if "acc" in modes:
            return "acc"
        raise ValueError(f"{mnemonic} requires an operand")

    op = " ".join(tokens).replace(" ", "")

    if op.upper() == "A":
        return "acc"

    if op.startswith("#"):
        return "imm"

    if op.startswith("("):
        if op.upper().endswith(",X)"):
            return "izx"
        if op.upper().endswith("),Y"):
            return "izy"
        return "paren"

    if op.upper().endswith(",X"):
        val = _parse_number(op[:-2])
        if val is not None and val < 0x100:
            return "zpx"
        return "absx"

    if op.upper().endswith(",Y"):
        val = _parse_number(op[:-2])
        if val is not None and val < 0x100:
            return "zpy"
        return "absy"

    val = _parse_number(op)
    if mnemonic in _OPCODES and "rel" in _OPCODES[mnemonic]:
        return "rel"
    if val is None:
        return "abs"  # label reference
    if val < 0x100:
        if mnemonic in _OPCODES and "zp" in _OPCODES[mnemonic]:
            return "zp"
        if mnemonic in _OPCODES and "abs" in _OPCODES[mnemonic]:
            return "abs"
        return "zp"
    return "abs"


def _encode_instruction(mnemonic: str, mode: str, operand_value: int | None) -> list[int]:
    """Return the byte sequence for a mnemonic + mode + operand."""
    modes = _OPCODES.get(mnemonic)
    if modes is None:
        raise ValueError(f"Unknown mnemonic: {mnemonic}")

    opcode = modes.get(mode)
    if opcode is None:
        raise ValueError(f"{mnemonic} does not support mode {mode}")

    length = 1
    if mode in ("imm", "zp", "zpx", "zpy", "izx", "izy", "izp", "rel"):
        length = 2
    elif mode in ("abs", "absx", "absy", "ind"):
        length = 3

    bytes_out = [opcode]

    if length == 2:
        if operand_value is None:
            raise ValueError(f"{mnemonic} requires an operand")
        bytes_out.append(operand_value & 0xFF)
    elif length == 3:
        if operand_value is None:
            raise ValueError(f"{mnemonic} requires an operand")
        bytes_out.append(operand_value & 0xFF)
        bytes_out.append((operand_value >> 8) & 0xFF)

    return bytes_out


# ---------------------------------------------------------------------------
# Two-pass parser
# ---------------------------------------------------------------------------

def parse_asm_file(path: str | Path) -> dict[str, list[str]]:
    """Parse a 6502 assembly file and return ``address -> [hex_bytes]``.

    Addresses are CPU addresses (e.g. ``8000``), not file offsets.
    """
    # Pass 1: collect labels
    labels: dict[str, int] = {}
    addr = 0x8000

    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            tokens = _tokenise(line)
            if not tokens:
                continue
            if tokens[0].endswith(":"):
                label_name = tokens[0][:-1]
                labels[label_name] = addr
                tokens = tokens[1:]
                if not tokens:
                    continue
            directive = tokens[0].lower()
            if directive == ".org":
                val = _parse_number(tokens[1])
                if val is None:
                    raise ValueError(f"Bad .org: {tokens[1]}")
                addr = val
            elif directive == ".byte":
                addr += len(tokens) - 1
            elif directive == ".word":
                addr += 2 * (len(tokens) - 1)
            else:
                mnemonic = tokens[0].upper()
                mode = _resolve_mode(mnemonic, tokens[1:])
                if mode == "paren":
                    mode = _resolve_paren_mode(mnemonic, tokens[1:])
                length = _mode_length(mode)
                addr += length

    # Pass 2: emit bytes
    result: dict[str, list[str]] = {}
    addr = 0x8000

    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            tokens = _tokenise(line)
            if not tokens:
                continue
            if tokens[0].endswith(":"):
                tokens = tokens[1:]
                if not tokens:
                    continue

            directive = tokens[0].lower()

            if directive == ".org":
                val = _parse_number(tokens[1])
                addr = val
                continue

            if directive == ".byte":
                for tok in tokens[1:]:
                    val = _resolve_value(tok, labels)
                    if val is None:
                        raise ValueError(f"Bad .byte operand: {tok}")
                    result[_addr_str(addr)] = [_byte_str(val)]
                    addr += 1
                continue

            if directive == ".word":
                for tok in tokens[1:]:
                    val = _resolve_value(tok, labels)
                    if val is None:
                        raise ValueError(f"Bad .word operand: {tok}")
                    result[_addr_str(addr)] = [_byte_str(val & 0xFF)]
                    addr += 1
                    result[_addr_str(addr)] = [_byte_str((val >> 8) & 0xFF)]
                    addr += 1
                continue

            mnemonic = tokens[0].upper()
            operand_tokens = tokens[1:]
            mode = _resolve_mode(mnemonic, operand_tokens)
            if mode == "paren":
                mode = _resolve_paren_mode(mnemonic, operand_tokens)

            operand_value = _resolve_operand_value(mode, operand_tokens, labels, addr)
            bytes_out = _encode_instruction(mnemonic, mode, operand_value)
            for b in bytes_out:
                result[_addr_str(addr)] = [_byte_str(b)]
                addr += 1

    return result


def _resolve_paren_mode(mnemonic: str, operand_tokens: list[str]) -> str:
    op_str = " ".join(operand_tokens).replace(" ", "")
    inner = op_str[1:-1]  # strip ()
    val = _parse_number(inner)
    if mnemonic == "JMP" and "ind" in _OPCODES.get(mnemonic, {}):
        return "ind"
    if val is not None and val < 0x100 and "izp" in _OPCODES.get(mnemonic, {}):
        return "izp"
    if "izx" in _OPCODES.get(mnemonic, {}):
        return "izx"
    return "ind"


def _mode_length(mode: str) -> int:
    if mode in ("imp", "acc"):
        return 1
    if mode in ("imm", "zp", "zpx", "zpy", "izx", "izy", "izp", "rel"):
        return 2
    return 3


def _resolve_value(token: str, labels: dict[str, int]) -> int | None:
    val = _parse_number(token)
    if val is not None:
        return val
    if token in labels:
        return labels[token]
    return None


def _resolve_operand_value(mode: str, operand_tokens: list[str], labels: dict[str, int], current_addr: int) -> int | None:
    op_str = " ".join(operand_tokens).replace(" ", "")
    if not op_str:
        return None

    if mode == "imm":
        return _resolve_value(op_str[1:], labels)
    if mode == "paren":
        inner = op_str[1:-1].replace(",X", "").replace(",x", "").replace(",Y", "").replace(",y", "")
        return _resolve_value(inner, labels)
    if mode == "izx":
        inner = op_str[1:-3]  # strip (...,X)
        return _resolve_value(inner, labels)
    if mode == "izy":
        inner = op_str[1:-3]  # strip (...),Y
        return _resolve_value(inner, labels)
    if mode == "rel":
        val = _resolve_value(op_str, labels)
        if val is None:
            return None
        # Compute signed 8-bit offset from instruction end (current_addr + 2)
        offset = val - (current_addr + 2)
        if offset < -128 or offset > 127:
            raise ValueError(f"Branch target out of range: {val:04X} from {current_addr:04X}")
        if offset < 0:
            offset += 256
        return offset
    if mode.endswith("x") or mode.endswith("y"):
        return _resolve_value(op_str[:-2], labels)

    return _resolve_value(op_str, labels)


def _addr_str(n: int) -> str:
    return f"{n:04X}"


def _byte_str(n: int) -> str:
    return f"{n:02X}"
