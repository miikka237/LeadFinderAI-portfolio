"""Smoke test: the offline demo runs end to end on the synthetic data."""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_demo_runs_offline(capsys):
    spec = importlib.util.spec_from_file_location("demo", os.path.join(ROOT, "demo.py"))
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)

    assert demo.main(["--no-export"]) == 0
    out = capsys.readouterr().out
    assert "ACCEPT: 2   REVIEW: 3   REJECT: 4" in out
    assert "9 unique candidate domains" in out
