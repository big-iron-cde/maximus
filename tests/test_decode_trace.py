"""Tests for maximus decode6502 control-flow trace."""

from maximus.decode6502 import (
    Instruction,
    decode_linear,
    format_decode_result,
    format_instruction,
    reconstruct_rom,
    trace_control_flow,
)
from maximus.models import Capture, CaptureResult, Cycle


def _make_branch_capture() -> Capture:
    """Capture with a simple branch loop:

    8000: A9 00     LDA #$00
    8002: F0 02     BEQ $8006
    8004: A9 01     LDA #$01
    8006: D0 FA     BNE $8002
    8008: DB        STP
    """
    cycles = [
        Cycle(seq=1, addr="FFFC", data="00", rw=0),
        Cycle(seq=2, addr="FFFD", data="80", rw=0),
        Cycle(seq=3, addr="8000", data="A9", rw=0),
        Cycle(seq=4, addr="8001", data="00", rw=0),
        Cycle(seq=5, addr="8002", data="F0", rw=0),
        Cycle(seq=6, addr="8003", data="02", rw=0),
        Cycle(seq=7, addr="8004", data="A9", rw=0),
        Cycle(seq=8, addr="8005", data="01", rw=0),
        Cycle(seq=9, addr="8006", data="D0", rw=0),
        Cycle(seq=10, addr="8007", data="FA", rw=0),
        Cycle(seq=11, addr="8008", data="DB", rw=0),
    ]
    return Capture(
        cycles=cycles,
        result=CaptureResult(cmd="read", reason="stp", cycles=11),
    )


def _make_unreachable_capture() -> Capture:
    """Capture with unreachable code after STP:

    8000: DB        STP
    8001: A9 05     LDA #$05   ; unreachable
    """
    cycles = [
        Cycle(seq=1, addr="FFFC", data="00", rw=0),
        Cycle(seq=2, addr="FFFD", data="80", rw=0),
        Cycle(seq=3, addr="8000", data="DB", rw=0),
        Cycle(seq=4, addr="8001", data="A9", rw=0),
        Cycle(seq=5, addr="8002", data="05", rw=0),
    ]
    return Capture(
        cycles=cycles,
        result=CaptureResult(cmd="read", reason="stp", cycles=5),
    )


def test_trace_branch_target_marking():
    capture = _make_branch_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    annotations = trace_control_flow(result)

    # BEQ at 8002 targets 8006
    assert annotations["8002"].flow_type == "branch"
    assert annotations["8002"].target_addr == "8006"

    # 8006 should be marked as a target
    assert annotations["8006"].is_target is True
    assert "8002" in annotations["8006"].target_of

    # BNE at 8006 targets 8002
    assert annotations["8006"].flow_type == "branch"
    assert annotations["8006"].target_addr == "8002"

    # 8002 should also be marked as a target (from BNE)
    assert "8006" in annotations["8002"].target_of


def test_trace_no_unreachable_in_branch_program():
    """Both branch paths are reachable in static analysis."""
    capture = _make_branch_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    annotations = trace_control_flow(result)

    # All instructions are reachable because BEQ adds both fall-through and target
    for inst in result.instructions:
        assert annotations[inst.addr].unreachable is False


def test_trace_unreachable_after_stp():
    capture = _make_unreachable_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    annotations = trace_control_flow(result)

    # STP at 8000 is reachable
    assert annotations["8000"].unreachable is False

    # Only STP was decoded (decoder stops at STP)
    assert len(result.instructions) == 1


def test_format_instruction_with_branch_annotation():
    inst = Instruction(addr="8002", bytes=["F0", "02"], mnemonic="BEQ", mode="rel", length=2)
    from maximus.decode6502 import FlowAnnotation
    ann = FlowAnnotation(flow_type="branch", target_addr="8006", is_target=False)
    line = format_instruction(inst, ann)
    assert "BEQ $8006" in line
    assert "→ 8006" in line


def test_format_instruction_with_target_annotation():
    inst = Instruction(addr="8006", bytes=["D0", "FA"], mnemonic="BNE", mode="rel", length=2)
    from maximus.decode6502 import FlowAnnotation
    ann = FlowAnnotation(flow_type="branch", target_addr="8002", is_target=True, target_of=["8002"])
    line = format_instruction(inst, ann)
    assert "*" in line


def test_format_instruction_unreachable():
    inst = Instruction(addr="8001", bytes=["A9", "05"], mnemonic="LDA", mode="imm", length=2)
    from maximus.decode6502 import FlowAnnotation
    ann = FlowAnnotation(unreachable=True)
    line = format_instruction(inst, ann)
    assert "[unreachable]" in line


def test_trace_jsr():
    """JSR marks target and fall-through."""
    cycles = [
        Cycle(seq=1, addr="FFFC", data="00", rw=0),
        Cycle(seq=2, addr="FFFD", data="80", rw=0),
        Cycle(seq=3, addr="8000", data="20", rw=0),  # JSR
        Cycle(seq=4, addr="8001", data="10", rw=0),
        Cycle(seq=5, addr="8002", data="80", rw=0),
        Cycle(seq=6, addr="8003", data="A9", rw=0),  # LDA #00 (fall-through)
        Cycle(seq=7, addr="8004", data="00", rw=0),
    ]
    capture = Capture(cycles=cycles)
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    annotations = trace_control_flow(result)

    assert annotations["8000"].flow_type == "jsr"
    assert annotations["8000"].target_addr == "8010"
    # Fall-through (8003) is reachable because JSR is assumed to return
    assert annotations["8003"].unreachable is False


def test_trace_jump():
    """JMP absolute marks target, fall-through unreachable."""
    cycles = [
        Cycle(seq=1, addr="FFFC", data="00", rw=0),
        Cycle(seq=2, addr="FFFD", data="80", rw=0),
        Cycle(seq=3, addr="8000", data="4C", rw=0),  # JMP abs
        Cycle(seq=4, addr="8001", data="10", rw=0),
        Cycle(seq=5, addr="8002", data="80", rw=0),
        Cycle(seq=6, addr="8003", data="A9", rw=0),  # unreachable LDA
        Cycle(seq=7, addr="8004", data="05", rw=0),
    ]
    capture = Capture(cycles=cycles)
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    annotations = trace_control_flow(result)

    assert annotations["8000"].flow_type == "jump"
    assert annotations["8000"].target_addr == "8010"
    # Fall-through after JMP is unreachable
    assert annotations["8003"].unreachable is True


def test_trace_format_full_output():
    capture = _make_branch_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    text = format_decode_result(result, trace=True)
    assert "→ 8006 *" in text  # BEQ target line
    assert "→ 8002 *" in text  # BNE target line


def test_trace_json_output():
    capture = _make_branch_capture()
    rom = reconstruct_rom(capture)
    result = decode_linear(rom)
    annotations = trace_control_flow(result)
    data = {addr: ann.to_dict() for addr, ann in annotations.items()}

    assert data["8002"]["flow_type"] == "branch"
    assert data["8002"]["target_addr"] == "8006"
    assert data["8006"]["is_target"] is True
