"""Tests for maximus.verify."""

from io import StringIO

import pytest

from maximus.models import Capture, Cycle
from maximus.verify import Expectation, VerifyResult, load_spec, verify


def _make_capture() -> Capture:
    cycles = [
        Cycle(seq=1, addr="8000", data="D8", rw=0),
        Cycle(seq=2, addr="8001", data="18", rw=0),
        Cycle(seq=3, addr="0200", data="02", rw=1),
        Cycle(seq=4, addr="8002", data="A9", rw=0),
    ]
    return Capture(cycles=cycles)


def test_verify_all_match():
    capture = _make_capture()
    expectations = [
        Expectation(addr="8000", data="D8", rw=0),
        Expectation(addr="8001", data="18", rw=0),
        Expectation(addr="0200", data="02", rw=1),
    ]
    result = verify(capture, expectations)
    assert result.pass_ is True
    assert result.matched == 3
    assert result.total == 3


def test_verify_tolerates_gaps():
    capture = _make_capture()
    expectations = [
        Expectation(addr="8000", data="D8", rw=0),
        Expectation(addr="8002", data="A9", rw=0),
    ]
    result = verify(capture, expectations)
    assert result.pass_ is True
    assert result.matched == 2


def test_verify_missing_event():
    capture = _make_capture()
    expectations = [
        Expectation(addr="8000", data="D8", rw=0),
        Expectation(addr="DEAD", data="BE", rw=0),
    ]
    result = verify(capture, expectations)
    assert result.pass_ is False
    assert result.matched == 1
    assert result.failed_at == 1
    assert "DEAD" in result.message


def test_verify_wrong_data():
    capture = _make_capture()
    expectations = [
        Expectation(addr="8000", data="FF", rw=0),
    ]
    result = verify(capture, expectations)
    assert result.pass_ is False
    assert "FF" in result.message


def test_verify_wrong_rw():
    capture = _make_capture()
    expectations = [
        Expectation(addr="8000", data="D8", rw=1),
    ]
    result = verify(capture, expectations)
    assert result.pass_ is False


def test_load_spec_yaml(tmp_path):
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        """\
expect:
  - addr: "8000"
    data: "D8"
    rw: 0
    label: reset_vector
""",
        encoding="utf-8",
    )
    expectations = load_spec(spec_path)
    assert len(expectations) == 1
    assert expectations[0].addr == "8000"
    assert expectations[0].data == "D8"
    assert expectations[0].rw == 0
    assert expectations[0].label == "reset_vector"


def test_load_spec_json(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        '{"expect":[{"addr":"0200","data":"02","rw":1}]}',
        encoding="utf-8",
    )
    expectations = load_spec(spec_path)
    assert len(expectations) == 1
    assert expectations[0].addr == "0200"
    assert expectations[0].rw == 1
