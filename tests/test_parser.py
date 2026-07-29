"""Tests for maximus.parser."""

from io import StringIO

import pytest

from maximus.models import CaptureResult, Cycle
from maximus.parser import parse_line, parse_stream


CYCLE_LINE = '{"v":1,"type":"event","event":"cycle","data":{"seq":1,"addr":"8000","data":"D8","rw":0}}'
RESULT_LINE = '{"v":1,"type":"result","cmd":"read","data":{"reason":"stp","cycles":39}}'


def test_parse_cycle_line():
    parsed = parse_line(CYCLE_LINE)
    assert isinstance(parsed, Cycle)
    assert parsed.seq == 1
    assert parsed.addr == "8000"
    assert parsed.data == "D8"
    assert parsed.rw == 0


def test_parse_result_line():
    parsed = parse_line(RESULT_LINE)
    assert isinstance(parsed, CaptureResult)
    assert parsed.cmd == "read"
    assert parsed.reason == "stp"
    assert parsed.cycles == 39


def test_parse_blank_line():
    assert parse_line("") is None
    assert parse_line("   ") is None


def test_parse_unrelated_line():
    line = '{"v":1,"type":"event","event":"monitor","addr":"8000"}'
    assert parse_line(line) is None


def test_parse_stream():
    stream = StringIO("\n".join([CYCLE_LINE, CYCLE_LINE, RESULT_LINE, ""]))
    capture = parse_stream(stream)
    assert len(capture) == 2
    assert capture.result is not None
    assert capture.result.cycles == 39


def test_parse_stream_missing_result():
    stream = StringIO(CYCLE_LINE)
    capture = parse_stream(stream)
    assert len(capture) == 1
    assert capture.result is None
