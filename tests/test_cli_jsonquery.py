"""Tests for maximus CLI jsonquery and check commands."""

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


def test_jsonquery_scalar_json(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["maximus", "jsonquery", '.result.reason', str(capture_file)])
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    assert captured.out.strip() == '"stp"'


def test_jsonquery_array_human(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    monkeypatch.setattr(
        sys, "argv",
        ["maximus", "jsonquery", '.cycles | filter(.rw == 1)', str(capture_file), "--format", "human"]
    )
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    assert "seq=3  addr=0200  data=02  rw=W" in captured.out


def test_jsonquery_cycles_size(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    monkeypatch.setattr(
        sys, "argv",
        ["maximus", "jsonquery", '.cycles | size()', str(capture_file)]
    )
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    assert captured.out.strip() == "3"


def test_check_all_pass_json(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    spec = tmp_path / "checks.txt"
    spec.write_text(
        'Ends with STP -> .result.reason == "stp"\n'
        'Exactly 3 cycles -> .cycles | size() == 3\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys, "argv",
        ["maximus", "check", str(capture_file), "--spec", str(spec)]
    )
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out.strip())
    assert result["pass"] is True
    assert len(result["results"]) == 2
    assert all(r["pass"] for r in result["results"])


def test_check_one_fails_json(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    spec = tmp_path / "checks.txt"
    spec.write_text(
        'Ends with STP -> .result.reason == "stp"\n'
        'Has 99 cycles -> .cycles | size() == 99\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys, "argv",
        ["maximus", "check", str(capture_file), "--spec", str(spec)]
    )
    ret = main()
    assert ret == 1

    captured = capsys.readouterr()
    result = json.loads(captured.out.strip())
    assert result["pass"] is False
    assert result["results"][0]["pass"] is True
    assert result["results"][1]["pass"] is False


def test_check_human_format(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    spec = tmp_path / "checks.txt"
    spec.write_text(
        'Ends with STP -> .result.reason == "stp"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys, "argv",
        ["maximus", "check", str(capture_file), "--spec", str(spec), "--format", "human"]
    )
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    assert "✅ Ends with STP" in captured.out
    assert "[PASS]" in captured.out


def test_check_comments_and_blank_lines_ignored(capsys, monkeypatch, tmp_path):
    capture_file = tmp_path / "capture.jsonl"
    capture_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    spec = tmp_path / "checks.txt"
    spec.write_text(
        "# This is a comment\n"
        "\n"
        'Ends with STP -> .result.reason == "stp"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys, "argv",
        ["maximus", "check", str(capture_file), "--spec", str(spec)]
    )
    ret = main()
    assert ret == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out.strip())
    assert result["pass"] is True
    assert len(result["results"]) == 1
