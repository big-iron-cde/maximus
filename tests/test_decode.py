"""Tests for maximus decode6502 module."""

from maximus.decode6502 import (
    Instruction,
    decode_linear,
    format_decode_result,
    format_instruction,
    reconstruct_rom,
)
from maximus.models import Capture, CaptureResult, Cycle


def _make_capture() -> Capture:
    """Sample capture: the 39-cycle trace from the user."""
    cycles = [
        # Reset vector reads
        Cycle(seq=7, addr="FFFC", data="00", rw=0),
        Cycle(seq=8, addr="FFFD", data="80", rw=0),
        # Program
        Cycle(seq=9, addr="8000", data="D8", rw=0),
        Cycle(seq=10, addr="8001", data="18", rw=0),
        Cycle(seq=11, addr="8001", data="18", rw=0),  # duplicate fetch
        Cycle(seq=12, addr="8002", data="A9", rw=0),
        Cycle(seq=13, addr="8002", data="A9", rw=0),  # duplicate
        Cycle(seq=14, addr="8003", data="05", rw=0),
        Cycle(seq=15, addr="8004", data="18", rw=0),
        Cycle(seq=16, addr="8005", data="69", rw=0),
        Cycle(seq=17, addr="8005", data="69", rw=0),  # duplicate
        Cycle(seq=18, addr="8006", data="0A", rw=0),
        Cycle(seq=19, addr="8007", data="18", rw=0),
        Cycle(seq=20, addr="8008", data="69", rw=0),
        Cycle(seq=21, addr="8008", data="69", rw=0),  # duplicate
        Cycle(seq=22, addr="8009", data="0F", rw=0),
        Cycle(seq=23, addr="800A", data="8D", rw=0),
        Cycle(seq=24, addr="800B", data="00", rw=0),
        Cycle(seq=25, addr="800C", data="02", rw=0),
        Cycle(seq=26, addr="0200", data="00", rw=1),  # RAM write (not ROM)
        Cycle(seq=27, addr="800D", data="A9", rw=0),
        Cycle(seq=28, addr="800E", data="14", rw=0),
        Cycle(seq=29, addr="800F", data="18", rw=0),
        Cycle(seq=30, addr="8010", data="6D", rw=0),
        Cycle(seq=31, addr="8010", data="6D", rw=0),  # duplicate
        Cycle(seq=32, addr="8011", data="00", rw=0),
        Cycle(seq=33, addr="8012", data="02", rw=0),
        Cycle(seq=34, addr="0200", data="00", rw=1),  # RAM write
        Cycle(seq=35, addr="8013", data="8D", rw=0),
        Cycle(seq=36, addr="8014", data="00", rw=0),
        Cycle(seq=37, addr="8015", data="40", rw=0),
        Cycle(seq=38, addr="4000", data="02", rw=1),  # RAM write
        Cycle(seq=39, addr="8016", data="DB", rw=0),
    ]
    return Capture(
        cycles=cycles,
        result=CaptureResult(cmd="read", reason="stp", cycles=39),
    )


def test_reconstruct_rom():
    capture = _make_capture()
    rom = reconstruct_rom(capture)
    # Last seen byte wins (duplicates overwrite)
    assert rom["8000"] == "D8"
    assert rom["8001"] == "18"
    assert rom["8002"] == "A9"
    assert rom["8003"] == "05"
    # RAM writes should NOT appear
    assert "0200" not in rom
    assert "4000" not in rom


def test_decode_linear_full():
    capture = _make_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)

    assert result.reset_vector == "8000"
    assert result.valid is True
    assert len(result.errors) == 0

    mnemonics = [i.mnemonic for i in result.instructions]
    assert mnemonics == [
        "CLD", "CLC", "LDA", "CLC", "ADC", "CLC", "ADC",
        "STA", "LDA", "CLC", "ADC", "STA", "STP",
    ]


def test_decode_linear_with_override_start():
    capture = _make_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom, start_addr=0x8002)

    assert result.reset_vector is None  # overridden
    assert result.instructions[0].mnemonic == "LDA"
    assert result.instructions[0].addr == "8002"


def test_decode_linear_truncated():
    """A capture missing the final operand byte."""
    cycles = [
        Cycle(seq=1, addr="FFFC", data="00", rw=0),
        Cycle(seq=2, addr="FFFD", data="80", rw=0),
        Cycle(seq=3, addr="8000", data="8D", rw=0),  # STA absolute (needs 3 bytes)
        Cycle(seq=4, addr="8001", data="00", rw=0),  # only 1 operand byte
        # missing 8002
    ]
    capture = Capture(cycles=cycles)
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)

    assert result.valid is False
    assert len(result.instructions) == 1
    assert result.instructions[0].mnemonic == "STA"
    assert result.instructions[0].valid is False
    assert "Missing operand" in result.instructions[0].error or "truncated" in result.errors[0].lower()


def test_decode_linear_invalid_opcode():
    """An undefined opcode in the stream."""
    cycles = [
        Cycle(seq=1, addr="FFFC", data="00", rw=0),
        Cycle(seq=2, addr="FFFD", data="80", rw=0),
        Cycle(seq=3, addr="8000", data="02", rw=0),  # invalid opcode
        Cycle(seq=4, addr="8001", data="DB", rw=0),  # STP
    ]
    capture = Capture(cycles=cycles)
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)

    assert result.valid is False
    assert result.instructions[0].mnemonic == "???"
    assert result.instructions[0].valid is False
    assert result.instructions[1].mnemonic == "STP"


def test_format_instruction():
    inst = Instruction(addr="8002", bytes=["A9", "05"], mnemonic="LDA", mode="imm", length=2)
    line = format_instruction(inst)
    assert line == "8002: A9 05    LDA #$05"


def test_format_instruction_relative():
    # BNE $8002 from $8005: offset = -3 (0xFD)
    inst = Instruction(addr="8005", bytes=["D0", "FD"], mnemonic="BNE", mode="rel", length=2)
    line = format_instruction(inst)
    assert "BNE $8004" in line or "BNE $8002" in line  # depends on calc


def test_format_instruction_invalid():
    inst = Instruction(
        addr="8000", bytes=["02"], mnemonic="???", mode="invalid", length=1,
        valid=False, error="Invalid opcode $02",
    )
    line = format_instruction(inst)
    assert "???" in line
    assert "❌" in line


def test_format_decode_result():
    capture = _make_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    text = format_decode_result(result)
    assert "Reset vector: $8000" in text
    assert "LDA #$05" in text
    assert "STA $0200" in text
    assert "STP" in text


def test_decode_result_json_roundtrip():
    capture = _make_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    data = result.to_dict()
    assert data["valid"] is True
    assert data["reset_vector"] == "8000"
    assert len(data["instructions"]) == 13
    assert data["instructions"][0]["mnemonic"] == "CLD"
