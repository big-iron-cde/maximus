"""Tests for maximus.asm_parser and source cross-check."""

import pytest

from maximus.asm_parser import parse_asm_file
from maximus.decode6502 import cross_check, reconstruct_rom
from maximus.models import Capture, CaptureResult, Cycle


@pytest.fixture
def sample_asm(tmp_path):
    path = tmp_path / "test.s"
    path.write_text(
        """\
        .org $8000
reset:  CLD
        CLC
        LDA #$05
        STA $0200
        STP
        .org $FFFC
        .word reset
""",
        encoding="utf-8",
    )
    return path


def test_parse_simple_instructions(sample_asm):
    result = parse_asm_file(sample_asm)
    assert result["8000"] == ["D8"]   # CLD
    assert result["8001"] == ["18"]   # CLC
    assert result["8002"] == ["A9"]   # LDA
    assert result["8003"] == ["05"]   # #$05
    assert result["8004"] == ["8D"]   # STA
    assert result["8005"] == ["00"]   # $0200 low
    assert result["8006"] == ["02"]   # $0200 high
    assert result["8007"] == ["DB"]   # STP
    assert result["FFFC"] == ["00"]   # reset vector low
    assert result["FFFD"] == ["80"]   # reset vector high


def test_parse_labels_and_branches(tmp_path):
    path = tmp_path / "branch.s"
    path.write_text(
        """\
        .org $8000
start:  LDA #$00
loop:   BEQ done
        LDA #$01
done:   BNE loop
        STP
        .org $FFFC
        .word start
""",
        encoding="utf-8",
    )
    result = parse_asm_file(path)
    assert result["8000"] == ["A9"]
    assert result["8001"] == ["00"]
    assert result["8002"] == ["F0"]   # BEQ
    assert result["8003"] == ["02"]   # offset to done (8006)
    assert result["8004"] == ["A9"]
    assert result["8005"] == ["01"]
    assert result["8006"] == ["D0"]   # BNE
    assert result["8007"] == ["FA"]   # offset to loop (8002) = -6


def test_parse_directives(tmp_path):
    path = tmp_path / "directives.s"
    path.write_text(
        """\
        .org $8000
        .byte $EA, 5
        .word $1234
""",
        encoding="utf-8",
    )
    result = parse_asm_file(path)
    assert result["8000"] == ["EA"]
    assert result["8001"] == ["05"]
    assert result["8002"] == ["34"]   # little-endian low
    assert result["8003"] == ["12"]   # little-endian high


def test_cross_check_match():
    """ROM and source match perfectly."""
    rom = {
        "8000": "D8",
        "8001": "18",
        "8002": "A9",
        "8003": "05",
    }
    source = {
        "8000": ["D8"],
        "8001": ["18"],
        "8002": ["A9"],
        "8003": ["05"],
    }
    result = cross_check(rom, source)
    assert result.valid is True
    assert result.matches == 4
    assert not result.mismatches
    assert not result.missing
    assert not result.extra


def test_cross_check_mismatch():
    """One byte differs."""
    rom = {
        "8000": "D8",
        "8001": "EA",  # wrong
        "8002": "A9",
    }
    source = {
        "8000": ["D8"],
        "8001": ["18"],
        "8002": ["A9"],
    }
    result = cross_check(rom, source)
    assert result.valid is False
    assert result.matches == 2
    assert len(result.mismatches) == 1
    assert result.mismatches[0] == {"addr": "8001", "expected": "18", "captured": "EA"}


def test_cross_check_missing():
    """Source expects a byte not in capture."""
    rom = {
        "8000": "D8",
    }
    source = {
        "8000": ["D8"],
        "8001": ["18"],
    }
    result = cross_check(rom, source)
    assert result.valid is False
    assert result.missing == ["8001"]


def test_cross_check_extra():
    """Capture has a byte not in source."""
    rom = {
        "8000": "D8",
        "8001": "18",
    }
    source = {
        "8000": ["D8"],
    }
    result = cross_check(rom, source)
    assert result.valid is False
    assert result.extra == ["8001"]


def test_cross_check_end_to_end(sample_asm):
    cycles = [
        Cycle(seq=1, addr="FFFC", data="00", rw=0),
        Cycle(seq=2, addr="FFFD", data="80", rw=0),
        Cycle(seq=3, addr="8000", data="D8", rw=0),
        Cycle(seq=4, addr="8001", data="18", rw=0),
        Cycle(seq=5, addr="8002", data="A9", rw=0),
        Cycle(seq=6, addr="8003", data="05", rw=0),
        Cycle(seq=7, addr="8004", data="8D", rw=0),
        Cycle(seq=8, addr="8005", data="00", rw=0),
        Cycle(seq=9, addr="8006", data="02", rw=0),
        Cycle(seq=10, addr="8007", data="DB", rw=0),
    ]
    capture = Capture(cycles=cycles, result=CaptureResult(cmd="read", reason="stp", cycles=10))
    rom = reconstruct_rom(capture)
    source = parse_asm_file(sample_asm)
    result = cross_check(rom, source)
    assert result.valid is True
    assert result.matches == 10
