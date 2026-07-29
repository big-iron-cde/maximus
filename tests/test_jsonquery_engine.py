"""Tests for maximus jsonquery engine."""

from maximus.jsonquery_engine import capture_to_json, format_result, run_query
from maximus.models import Capture, CaptureResult, Cycle


def _make_capture() -> Capture:
    cycles = [
        Cycle(seq=1, addr="8000", data="D8", rw=0),
        Cycle(seq=2, addr="8001", data="18", rw=0),
        Cycle(seq=3, addr="0200", data="02", rw=1),
    ]
    return Capture(
        cycles=cycles,
        result=CaptureResult(cmd="read", reason="stp", cycles=3),
    )


def test_capture_to_json():
    capture = _make_capture()
    data = capture_to_json(capture)
    assert data["cycles"][0] == {"seq": 1, "addr": "8000", "data": "D8", "rw": 0}
    assert data["result"] == {"cmd": "read", "reason": "stp", "cycles": 3}


def test_run_query_result_reason():
    capture = _make_capture()
    result = run_query(capture, '.result.reason')
    assert result == "stp"


def test_run_query_cycles_size():
    capture = _make_capture()
    result = run_query(capture, '.cycles | size()')
    assert result == 3


def test_run_query_filter_addr():
    capture = _make_capture()
    result = run_query(capture, '.cycles | filter(.addr == "0200")')
    assert len(result) == 1
    assert result[0]["addr"] == "0200"


def test_run_query_filter_rw():
    capture = _make_capture()
    result = run_query(capture, '.cycles | filter(.rw == 1)')
    assert len(result) == 1
    assert result[0]["data"] == "02"


def test_format_result_json_scalar():
    assert format_result(39, "json") == "39"
    assert format_result("stp", "json") == '"stp"'
    assert format_result(True, "json") == "true"


def test_format_result_human_scalar():
    assert format_result(39, "human") == "39"
    assert format_result("stp", "human") == "stp"
    assert format_result(True, "human") == "true"
    assert format_result(False, "human") == "false"


def test_format_result_human_list_of_cycles():
    cycles = [
        {"seq": 1, "addr": "8000", "data": "D8", "rw": 0},
        {"seq": 2, "addr": "0200", "data": "02", "rw": 1},
    ]
    output = format_result(cycles, "human")
    assert "seq=1  addr=8000  data=D8  rw=R" in output
    assert "seq=2  addr=0200  data=02  rw=W" in output


def test_format_result_human_single_cycle():
    cycle = {"seq": 1, "addr": "8000", "data": "D8", "rw": 0}
    output = format_result(cycle, "human")
    assert "seq=1  addr=8000  data=D8  rw=R" == output


def test_format_result_human_dict():
    obj = {"foo": "8000", "bar": "D8"}
    output = format_result(obj, "human")
    assert "foo: 8000" in output
    assert "bar: D8" in output
