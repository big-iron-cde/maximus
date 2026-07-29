"""6502/65C02 instruction stream decoder for maximus.

Reconstructs a ROM image from captured bus cycles and performs linear
disassembly + validation.  Opcode metadata is ported from Romulan's
assembler / build_rom modules so Maximus stays standalone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maximus.models import Capture, Cycle


# ---------------------------------------------------------------------------
# Opcode metadata (ported from Romulan)
# ---------------------------------------------------------------------------

# Addressing mode identifiers
_IMP = "imp"    # implied
_ACC = "acc"    # accumulator
_IMM = "imm"    # immediate
_ZP = "zp"      # zero page
_ZPX = "zpx"    # zero page,X
_ZPY = "zpy"    # zero page,Y
_ABS = "abs"    # absolute
_ABSX = "absx"  # absolute,X
_ABSY = "absy"  # absolute,Y
_IND = "ind"    # indirect (JMP only)
_IZX = "izx"    # (zp,X)
_IZY = "izy"    # (zp),Y
_IZP = "izp"    # (zp) — 65C02
_REL = "rel"    # relative (branches)

_MODE_SIZE = {
    _IMP: 1, _ACC: 1,
    _IMM: 2, _ZP: 2, _ZPX: 2, _ZPY: 2, _IZX: 2, _IZY: 2, _IZP: 2, _REL: 2,
    _ABS: 3, _ABSX: 3, _ABSY: 3, _IND: 3,
}

_OPCODES: dict[str, dict[str, int]] = {
    "ADC": {_IMM: 0x69, _ZP: 0x65, _ZPX: 0x75, _ABS: 0x6D, _ABSX: 0x7D,
            _ABSY: 0x79, _IZX: 0x61, _IZY: 0x71, _IZP: 0x72},
    "AND": {_IMM: 0x29, _ZP: 0x25, _ZPX: 0x35, _ABS: 0x2D, _ABSX: 0x3D,
            _ABSY: 0x39, _IZX: 0x21, _IZY: 0x31, _IZP: 0x32},
    "ASL": {_ACC: 0x0A, _ZP: 0x06, _ZPX: 0x16, _ABS: 0x0E, _ABSX: 0x1E},
    "BCC": {_REL: 0x90},
    "BCS": {_REL: 0xB0},
    "BEQ": {_REL: 0xF0},
    "BIT": {_IMM: 0x89, _ZP: 0x24, _ZPX: 0x34, _ABS: 0x2C, _ABSX: 0x3C},
    "BMI": {_REL: 0x30},
    "BNE": {_REL: 0xD0},
    "BPL": {_REL: 0x10},
    "BRA": {_REL: 0x80},
    "BRK": {_IMP: 0x00},
    "BVC": {_REL: 0x50},
    "BVS": {_REL: 0x70},
    "CLC": {_IMP: 0x18},
    "CLD": {_IMP: 0xD8},
    "CLI": {_IMP: 0x58},
    "CLV": {_IMP: 0xB8},
    "CMP": {_IMM: 0xC9, _ZP: 0xC5, _ZPX: 0xD5, _ABS: 0xCD, _ABSX: 0xDD,
            _ABSY: 0xD9, _IZX: 0xC1, _IZY: 0xD1, _IZP: 0xD2},
    "CPX": {_IMM: 0xE0, _ZP: 0xE4, _ABS: 0xEC},
    "CPY": {_IMM: 0xC0, _ZP: 0xC4, _ABS: 0xCC},
    "DEC": {_ACC: 0x3A, _ZP: 0xC6, _ZPX: 0xD6, _ABS: 0xCE, _ABSX: 0xDE},
    "DEX": {_IMP: 0xCA},
    "DEY": {_IMP: 0x88},
    "EOR": {_IMM: 0x49, _ZP: 0x45, _ZPX: 0x55, _ABS: 0x4D, _ABSX: 0x5D,
            _ABSY: 0x59, _IZX: 0x41, _IZY: 0x51, _IZP: 0x52},
    "INC": {_ACC: 0x1A, _ZP: 0xE6, _ZPX: 0xF6, _ABS: 0xEE, _ABSX: 0xFE},
    "INX": {_IMP: 0xE8},
    "INY": {_IMP: 0xC8},
    "JMP": {_ABS: 0x4C, _IND: 0x6C},
    "JSR": {_ABS: 0x20},
    "LDA": {_IMM: 0xA9, _ZP: 0xA5, _ZPX: 0xB5, _ABS: 0xAD, _ABSX: 0xBD,
            _ABSY: 0xB9, _IZX: 0xA1, _IZY: 0xB1, _IZP: 0xB2},
    "LDX": {_IMM: 0xA2, _ZP: 0xA6, _ZPY: 0xB6, _ABS: 0xAE, _ABSY: 0xBE},
    "LDY": {_IMM: 0xA0, _ZP: 0xA4, _ZPX: 0xB4, _ABS: 0xAC, _ABSX: 0xBC},
    "LSR": {_ACC: 0x4A, _ZP: 0x46, _ZPX: 0x56, _ABS: 0x4E, _ABSX: 0x5E},
    "NOP": {_IMP: 0xEA},
    "ORA": {_IMM: 0x09, _ZP: 0x05, _ZPX: 0x15, _ABS: 0x0D, _ABSX: 0x1D,
            _ABSY: 0x19, _IZX: 0x01, _IZY: 0x11, _IZP: 0x12},
    "PHA": {_IMP: 0x48},
    "PHP": {_IMP: 0x08},
    "PHX": {_IMP: 0xDA},
    "PHY": {_IMP: 0x5A},
    "PLA": {_IMP: 0x68},
    "PLP": {_IMP: 0x28},
    "PLX": {_IMP: 0xFA},
    "PLY": {_IMP: 0x7A},
    "ROL": {_ACC: 0x2A, _ZP: 0x26, _ZPX: 0x36, _ABS: 0x2E, _ABSX: 0x3E},
    "ROR": {_ACC: 0x6A, _ZP: 0x66, _ZPX: 0x76, _ABS: 0x6E, _ABSX: 0x7E},
    "RTI": {_IMP: 0x40},
    "RTS": {_IMP: 0x60},
    "SBC": {_IMM: 0xE9, _ZP: 0xE5, _ZPX: 0xF5, _ABS: 0xED, _ABSX: 0xFD,
            _ABSY: 0xF9, _IZX: 0xE1, _IZY: 0xF1, _IZP: 0xF2},
    "SEC": {_IMP: 0x38},
    "SED": {_IMP: 0xF8},
    "SEI": {_IMP: 0x78},
    "STA": {_ZP: 0x85, _ZPX: 0x95, _ABS: 0x8D, _ABSX: 0x9D, _ABSY: 0x99,
            _IZX: 0x81, _IZY: 0x91, _IZP: 0x92},
    "STP": {_IMP: 0xDB},
    "STX": {_ZP: 0x86, _ZPY: 0x96, _ABS: 0x8E},
    "STY": {_ZP: 0x84, _ZPX: 0x94, _ABS: 0x8C},
    "STZ": {_ZP: 0x64, _ZPX: 0x74, _ABS: 0x9C, _ABSX: 0x9E},
    "TAX": {_IMP: 0xAA},
    "TAY": {_IMP: 0xA8},
    "TRB": {_ZP: 0x14, _ABS: 0x1C},
    "TSB": {_ZP: 0x04, _ABS: 0x0C},
    "TSX": {_IMP: 0xBA},
    "TXA": {_IMP: 0x8A},
    "TXS": {_IMP: 0x9A},
    "TYA": {_IMP: 0x98},
    "WAI": {_IMP: 0xCB},
}

# Build reverse lookup: opcode byte -> (mnemonic, mode, length)
_OPCODE_INFO: dict[int, tuple[str, str, int]] = {}
for _mnemonic, _modes in _OPCODES.items():
    for _mode, _opcode in _modes.items():
        _length = _MODE_SIZE[_mode]
        _OPCODE_INFO[_opcode] = (_mnemonic, _mode, _length)

# W65C02 instruction lengths (same as Romulan's _OPCODE_LENGTH)
_OPCODE_LENGTH: list[int] = [
    # 0x00-0x0F
    2, 2, 1, 1, 2, 2, 2, 2, 1, 2, 1, 1, 3, 3, 3, 3,
    # 0x10-0x1F
    2, 2, 2, 1, 2, 2, 2, 2, 1, 3, 1, 1, 3, 3, 3, 3,
    # 0x20-0x2F
    3, 2, 1, 1, 2, 2, 2, 2, 1, 2, 1, 1, 3, 3, 3, 3,
    # 0x30-0x3F
    2, 2, 2, 1, 2, 2, 2, 2, 1, 3, 1, 1, 3, 3, 3, 3,
    # 0x40-0x4F
    1, 2, 1, 1, 2, 2, 2, 2, 1, 2, 1, 1, 3, 3, 3, 3,
    # 0x50-0x5F
    2, 2, 2, 1, 2, 2, 2, 2, 1, 3, 1, 1, 1, 3, 3, 3,
    # 0x60-0x6F
    1, 2, 1, 1, 2, 2, 2, 2, 1, 2, 1, 1, 3, 3, 3, 3,
    # 0x70-0x7F
    2, 2, 2, 1, 2, 2, 2, 2, 1, 3, 1, 1, 3, 3, 3, 3,
    # 0x80-0x8F
    2, 2, 1, 1, 2, 2, 2, 2, 1, 2, 1, 1, 3, 3, 3, 3,
    # 0x90-0x9F
    2, 2, 2, 1, 2, 2, 2, 2, 1, 3, 1, 1, 3, 3, 3, 3,
    # 0xA0-0xAF
    2, 2, 2, 1, 2, 2, 2, 2, 1, 2, 1, 1, 3, 3, 3, 3,
    # 0xB0-0xBF
    2, 2, 2, 1, 2, 2, 2, 2, 1, 3, 1, 1, 3, 3, 3, 3,
    # 0xC0-0xCF
    2, 2, 1, 1, 2, 2, 2, 2, 1, 2, 1, 1, 3, 3, 3, 3,
    # 0xD0-0xDF
    2, 2, 2, 1, 2, 2, 2, 2, 1, 3, 1, 1, 1, 3, 3, 3,
    # 0xE0-0xEF
    2, 2, 1, 1, 2, 2, 2, 2, 1, 2, 1, 1, 3, 3, 3, 3,
    # 0xF0-0xFF
    2, 2, 2, 1, 2, 2, 2, 2, 1, 3, 1, 1, 1, 3, 3, 3,
]

_INVALID_OPCODES = frozenset({
    0x02, 0x03, 0x0B, 0x13, 0x1B, 0x22, 0x23, 0x2B, 0x33,
    0x3B, 0x42, 0x43, 0x44, 0x4B, 0x53, 0x54, 0x5B, 0x5C,
    0x62, 0x63, 0x6B, 0x73, 0x7B, 0x82, 0x83, 0x8B, 0x93,
    0x9B, 0xA3, 0xAB, 0xB3, 0xBB, 0xC2, 0xC3, 0xD3, 0xD4,
    0xDC, 0xE2, 0xE3, 0xEB, 0xF3, 0xF4, 0xFB, 0xFC,
})


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Instruction:
    """A decoded 6502/65C02 instruction."""

    addr: str          # 4-digit hex address (e.g. "8000")
    bytes: list[str]   # hex bytes (opcode + operands)
    mnemonic: str      # e.g. "LDA"
    mode: str          # addressing mode tag
    length: int        # total bytes
    valid: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "addr": self.addr,
            "bytes": self.bytes,
            "mnemonic": self.mnemonic,
            "mode": self.mode,
            "length": self.length,
            "valid": self.valid,
            "error": self.error,
        }


@dataclass
class DecodeResult:
    """Outcome of linear decode."""

    instructions: list[Instruction]
    reset_vector: str | None = None
    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instructions": [i.to_dict() for i in self.instructions],
            "reset_vector": self.reset_vector,
            "valid": self.valid,
            "errors": self.errors,
        }


@dataclass
class FlowAnnotation:
    """Control-flow metadata attached to an instruction."""

    is_target: bool = False          # is this address jumped/branched to?
    target_of: list[str] = field(default_factory=list)  # source addresses
    flow_type: str | None = None     # "branch", "jump", "jsr", "return", "stop"
    target_addr: str | None = None   # computed destination address
    unreachable: bool = False        # no execution path reaches this

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_target": self.is_target,
            "target_of": self.target_of,
            "flow_type": self.flow_type,
            "target_addr": self.target_addr,
            "unreachable": self.unreachable,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_int(s: str) -> int:
    return int(s, 16)


def _int_hex(n: int) -> str:
    return f"{n:04X}"


def _byte_hex(n: int) -> str:
    return f"{n:02X}"


# ---------------------------------------------------------------------------
# ROM reconstruction
# ---------------------------------------------------------------------------

def reconstruct_rom(capture: Capture) -> dict[str, str]:
    """Build a ROM image dict from ROM-read cycles (addr >= $8000, rw=0).

    In a real capture the same address may be read multiple times (opcode
    fetches + operand fetches can overlap).  We keep the *last* seen byte
    because it is the definitive value the Pico drove on the bus.
    """
    rom: dict[str, str] = {}
    for cycle in capture.cycles:
        if cycle.is_read() and _hex_int(cycle.addr) >= 0x8000:
            rom[cycle.addr] = cycle.data
    return rom


# ---------------------------------------------------------------------------
# Linear decode
# ---------------------------------------------------------------------------

def decode_linear(rom: dict[str, str], start_addr: int | None = None) -> DecodeResult:
    """Disassemble the instruction stream starting from *start_addr*.

    If *start_addr* is ``None``, it is read from the reset vector at
    ``$FFFC/$FFFD`` (if present in the ROM image).
    """
    result = DecodeResult(instructions=[])

    # Determine start address from reset vector
    if start_addr is None:
        lo = rom.get("FFFC")
        hi = rom.get("FFFD")
        if lo is not None and hi is not None:
            start_addr = (_hex_int(lo) | (_hex_int(hi) << 8))
            result.reset_vector = _int_hex(start_addr)
        else:
            result.errors.append("Reset vector ($FFFC/$FFFD) not found in capture")
            result.valid = False
            return result

    addr = start_addr
    seen: set[int] = set()

    while True:
        addr_str = _int_hex(addr)
        if addr in seen:
            # Loop detected (simple protection)
            result.errors.append(f"Loop detected at {addr_str}")
            result.valid = False
            break
        seen.add(addr)

        op_byte_str = rom.get(addr_str)
        if op_byte_str is None:
            result.errors.append(f"Missing byte at {addr_str} — truncated stream?")
            result.valid = False
            break

        op_byte = _hex_int(op_byte_str)

        # Check for invalid opcode
        if op_byte in _INVALID_OPCODES:
            length = _OPCODE_LENGTH[op_byte]
            inst = Instruction(
                addr=addr_str,
                bytes=[op_byte_str],
                mnemonic="???",
                mode="invalid",
                length=length,
                valid=False,
                error=f"Invalid opcode ${op_byte_str}",
            )
            result.instructions.append(inst)
            result.errors.append(f"Invalid opcode ${op_byte_str} at {addr_str}")
            result.valid = False
            addr += length
            continue

        # Look up opcode info
        info = _OPCODE_INFO.get(op_byte)
        if info is None:
            # Should not happen for valid 6502, but handle defensively
            length = _OPCODE_LENGTH[op_byte]
            inst = Instruction(
                addr=addr_str,
                bytes=[op_byte_str],
                mnemonic="???",
                mode="unknown",
                length=length,
                valid=False,
                error=f"Unknown opcode ${op_byte_str}",
            )
            result.instructions.append(inst)
            result.errors.append(f"Unknown opcode ${op_byte_str} at {addr_str}")
            result.valid = False
            addr += length
            continue

        mnemonic, mode, length = info

        # Gather operand bytes
        inst_bytes = [op_byte_str]
        valid = True
        error: str | None = None
        for offset in range(1, length):
            operand_addr_str = _int_hex(addr + offset)
            operand_byte = rom.get(operand_addr_str)
            if operand_byte is None:
                valid = False
                error = f"Missing operand byte at {operand_addr_str}"
                break
            inst_bytes.append(operand_byte)

        inst = Instruction(
            addr=addr_str,
            bytes=inst_bytes,
            mnemonic=mnemonic,
            mode=mode,
            length=length,
            valid=valid,
            error=error,
        )
        result.instructions.append(inst)

        if not valid:
            result.errors.append(error or f"Truncated instruction at {addr_str}")
            result.valid = False
            break

        # Stop at STP
        if op_byte == 0xDB:
            break

        addr += length

    return result


# ---------------------------------------------------------------------------
# Control-flow trace
# ---------------------------------------------------------------------------

_BRANCH_MNEMONICS = frozenset({
    "BCC", "BCS", "BEQ", "BMI", "BNE", "BPL", "BRA", "BVC", "BVS",
})

_RETURN_MNEMONICS = frozenset({"RTS", "RTI"})
_STOP_MNEMONICS = frozenset({"STP", "BRK"})


def _compute_target(inst: Instruction) -> str | None:
    """Compute the destination address for a control-flow instruction."""
    mnemonic = inst.mnemonic
    mode = inst.mode

    # Branches: target = PC + 2 + signed_offset
    if mnemonic in _BRANCH_MNEMONICS and len(inst.bytes) == 2:
        offset = _hex_int(inst.bytes[1])
        if offset >= 0x80:
            offset -= 0x100
        target = _hex_int(inst.addr) + 2 + offset
        return _int_hex(target)

    # JMP absolute / JSR absolute: target = operand word
    if mnemonic in ("JMP", "JSR") and mode == _ABS and len(inst.bytes) == 3:
        target = (_hex_int(inst.bytes[2]) << 8) | _hex_int(inst.bytes[1])
        return _int_hex(target)

    # JMP indirect: we can't resolve without reading memory
    if mnemonic == "JMP" and mode == _IND:
        return None

    return None


def trace_control_flow(result: DecodeResult) -> dict[str, FlowAnnotation]:
    """Annotate every instruction with control-flow metadata.

    Returns a mapping ``address -> FlowAnnotation``.
    """
    annotations: dict[str, FlowAnnotation] = {}
    addr_to_idx: dict[str, int] = {}

    for idx, inst in enumerate(result.instructions):
        addr_to_idx[inst.addr] = idx
        annotations[inst.addr] = FlowAnnotation()

    for inst in result.instructions:
        ann = annotations[inst.addr]
        mnemonic = inst.mnemonic

        if mnemonic in _BRANCH_MNEMONICS:
            ann.flow_type = "branch"
        elif mnemonic == "JMP":
            ann.flow_type = "jump"
        elif mnemonic == "JSR":
            ann.flow_type = "jsr"
        elif mnemonic in _RETURN_MNEMONICS:
            ann.flow_type = "return"
        elif mnemonic in _STOP_MNEMONICS:
            ann.flow_type = "stop"

        target = _compute_target(inst)
        if target is not None:
            ann.target_addr = target
            if target in annotations:
                annotations[target].is_target = True
                annotations[target].target_of.append(inst.addr)

    # Simple reachability analysis
    reachable: set[str] = set()
    if result.reset_vector:
        reachable.add(result.reset_vector)

    for idx, inst in enumerate(result.instructions):
        addr = inst.addr
        if addr not in reachable and idx == 0:
            reachable.add(addr)  # first instruction is always reachable

        if addr in reachable:
            ann = annotations[addr]
            # Sequential flow
            if ann.flow_type not in ("jump", "return", "stop"):
                if idx + 1 < len(result.instructions):
                    next_addr = result.instructions[idx + 1].addr
                    reachable.add(next_addr)
            # Branch / JSR target
            if ann.target_addr is not None:
                reachable.add(ann.target_addr)

    for inst in result.instructions:
        if inst.addr not in reachable:
            annotations[inst.addr].unreachable = True

    return annotations


# ---------------------------------------------------------------------------
# Source cross-check
# ---------------------------------------------------------------------------

@dataclass
class CrossCheckResult:
    """Result of comparing a capture against a source assembly file."""

    matches: int = 0
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.mismatches and not self.missing and not self.extra

    def to_dict(self) -> dict[str, Any]:
        return {
            "matches": self.matches,
            "mismatches": self.mismatches,
            "missing": self.missing,
            "extra": self.extra,
            "valid": self.valid,
        }


def cross_check(rom: dict[str, str], source_bytes: dict[str, list[str]]) -> CrossCheckResult:
    """Compare reconstructed *rom* against expected *source_bytes*.

    *source_bytes* is ``address -> [hex_byte]`` from :func:`parse_asm_file`.
    *rom* is ``address -> hex_byte`` from :func:`reconstruct_rom`.
    """
    result = CrossCheckResult()

    # Flatten source_bytes (each address has exactly one byte in our parser)
    expected: dict[str, str] = {}
    for addr, bytes_list in source_bytes.items():
        if bytes_list:
            expected[addr] = bytes_list[0]

    all_addrs = set(rom.keys()) | set(expected.keys())

    for addr in sorted(all_addrs, key=lambda s: int(s, 16)):
        if addr in expected and addr in rom:
            if rom[addr].upper() == expected[addr].upper():
                result.matches += 1
            else:
                result.mismatches.append({
                    "addr": addr,
                    "expected": expected[addr],
                    "captured": rom[addr],
                })
        elif addr in expected:
            result.missing.append(addr)
        else:
            result.extra.append(addr)

    return result


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_instruction(inst: Instruction, ann: FlowAnnotation | None = None) -> str:
    """Human-readable single-line representation.

    Optional *ann* adds control-flow annotations.
    """
    hex_part = " ".join(inst.bytes)
    padding = " " * (9 - len(hex_part))  # align mnemonics

    def _byte(n: int) -> str:
        return inst.bytes[n] if n < len(inst.bytes) else "??"

    mode_suffix = {
        _IMM: f"#${_byte(1)}",
        _ZP: f"${_byte(1)}",
        _ZPX: f"${_byte(1)},X",
        _ZPY: f"${_byte(1)},Y",
        _ABS: f"${_byte(2)}{_byte(1)}",
        _ABSX: f"${_byte(2)}{_byte(1)},X",
        _ABSY: f"${_byte(2)}{_byte(1)},Y",
        _IND: f"(${_byte(2)}{_byte(1)})",
        _IZX: f"(${_byte(1)},X)",
        _IZY: f"(${_byte(1)}),Y",
        _IZP: f"(${_byte(1)})",
        _REL: "",  # relative offset printed separately if needed
    }

    operand = mode_suffix.get(inst.mode, "")
    if inst.mode == _REL and len(inst.bytes) == 2:
        offset = _hex_int(inst.bytes[1])
        if offset >= 0x80:
            offset -= 0x100
        target = _hex_int(inst.addr) + 2 + offset
        operand = f"${_int_hex(target)}"

    # Control-flow arrows
    arrow = ""
    if ann is not None:
        if ann.flow_type == "branch":
            arrow = f" → {ann.target_addr}"
        elif ann.flow_type == "jump":
            arrow = f" → {ann.target_addr}" if ann.target_addr else " → ?"
        elif ann.flow_type == "jsr":
            arrow = f" → {ann.target_addr}"

    target_mark = " *" if ann is not None and ann.is_target else ""
    unreachable_mark = " [unreachable]" if ann is not None and ann.unreachable else ""

    line = f"{inst.addr}: {hex_part}{padding}{inst.mnemonic} {operand}{arrow}".rstrip()
    line += target_mark + unreachable_mark
    if not inst.valid:
        line += f"  ❌ {inst.error}"
    return line


def format_decode_result(result: DecodeResult, trace: bool = False) -> str:
    """Full human-readable decode report.

    *trace* enables control-flow annotations.
    """
    lines: list[str] = []
    if result.reset_vector:
        lines.append(f"Reset vector: ${result.reset_vector}")

    annotations = trace_control_flow(result) if trace else {}

    for inst in result.instructions:
        ann = annotations.get(inst.addr)
        lines.append(format_instruction(inst, ann))

    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for err in result.errors:
            lines.append(f"  - {err}")
    return "\n".join(lines)
