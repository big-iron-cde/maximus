"""Tests for maximus CLI."""

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

from maximus.cli import main


SAMPLE_NDJSON = """\
{"v":1,"type":"event","event":"cycle","data":{"seq":1,"addr":"8000","data":"D8","rw":0}}
{"v":1,"type":"event","event":"cycle","data":{"seq":2,"addr":"8001","data":"18","rw":0}}
{"v":1,"type":"event","event":"cycle","data":{"seq":3,"addr":"0200","data":"02","rw":1}}
{"v":1,"type":"result","cmd":"read","data":{"reason":"stp","cycles":3}}
"""


def test_parse_subcommand(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["maximus", "parse", str(capture_file)])
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    assert "Cycles captured: 3" in captured.out
    assert "seq=1  addr=8000  data=D8  rw=R" in captured.out
    assert "seq=3  addr=0200  data=02  rw=W" in captured.out


def test_query_subcommand_addr_filter(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["maximus", "query", str(capture_file), "--addr", "8000"])
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert "addr=8000" in lines[0]


def test_query_subcommand_rw_filter(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["maximus", "query", str(capture_file), "--rw", "1"])
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert "rw=W" in lines[0]


def test_verify_subcommand_pass(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    spec = {
        "expect": [
            {"addr": "8000", "data": "D8", "rw": 0},
            {"addr": "8001", "data": "18", "rw": 0},
            {"addr": "0200", "data": "02", "rw": 1},
        ]
    }
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["maximus", "verify", str(capture_file), "--spec", str(spec_file)])
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    assert "PASS" in captured.out


def test_verify_subcommand_fail(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    spec = {
        "expect": [
            {"addr": "8000", "data": "D8", "rw": 0},
            {"addr": "DEAD", "data": "BE", "rw": 0},
        ]
    }
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["maximus", "verify", str(capture_file), "--spec", str(spec_file)])
    ret = main()
    assert ret == 1

    captured = capsys.readouterr()
    assert "FAIL" in captured.out
    assert "DEAD" in captured.out


def test_verify_subcommand_json(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    spec = {"expect": [{"addr": "8000", "data": "D8", "rw": 0}]}
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    monkeypatch.setattr(
        sys, "argv",
        ["maximus", "verify", str(capture_file), "--spec", str(spec_file), "--json"]
    )
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out.strip())
    assert result["pass"] is True
    assert result["matched"] == 1
