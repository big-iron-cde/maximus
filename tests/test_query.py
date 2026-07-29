"""Tests for maximus.query."""

from maximus.models import Capture, Cycle
from maximus.query import by_address, filter_cycles, reads, writes


def _make_capture() -> Capture:
    cycles = [
        Cycle(seq=1, addr="8000", data="D8", rw=0),
        Cycle(seq=2, addr="8001", data="18", rw=0),
        Cycle(seq=3, addr="0200", data="02", rw=1),
        Cycle(seq=4, addr="8000", data="EA", rw=0),
    ]
    return Capture(cycles=cycles)


def test_reads():
    capture = _make_capture()
    assert len(reads(capture)) == 3


def test_writes():
    capture = _make_capture()
    assert len(writes(capture)) == 1
    assert writes(capture)[0].addr == "0200"


def test_by_address():
    capture = _make_capture()
    found = by_address(capture, "8000")
    assert len(found) == 2
    assert found[0].seq == 1
    assert found[1].seq == 4


def test_filter_cycles_addr():
    capture = _make_capture()
    found = filter_cycles(capture, addr="8001")
    assert len(found) == 1
    assert found[0].seq == 2


def test_filter_cycles_data():
    capture = _make_capture()
    found = filter_cycles(capture, data="02")
    assert len(found) == 1
    assert found[0].rw == 1


def test_filter_cycles_rw():
    capture = _make_capture()
    found = filter_cycles(capture, rw=0)
    assert len(found) == 3


def test_filter_cycles_seq_range():
    capture = _make_capture()
    found = filter_cycles(capture, min_seq=2, max_seq=3)
    assert len(found) == 2
    assert found[0].seq == 2
    assert found[1].seq == 3


def test_filter_cycles_case_insensitive():
    capture = _make_capture()
    found = filter_cycles(capture, addr="8000")
    found_lower = filter_cycles(capture, addr="8000")
    assert len(found) == len(found_lower)
