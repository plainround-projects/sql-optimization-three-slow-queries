"""The lesson's scenario through the command-line programs, as the Makefile runs them (make up db first)."""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.e2e


def program(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", f"slow_queries.interfaces.{module}", *args],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=900,
        check=False,
    )


def test_the_health_command_is_green_on_the_seeded_database():
    result = program("health_cli")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok postgres: 1,000,000 orders" in result.stdout


def test_the_replay_writes_every_plan_and_a_results_table(tmp_path):
    result = program("run_cli", "--output-dir", str(tmp_path), "--repetitions", "1")
    assert result.returncode == 0, result.stderr
    notes = (tmp_path / "results.md").read_text()
    assert "| q1 day query |" in notes
    assert "| idx_orders_listing only (idx_orders_customer_created dropped) |" in notes
    assert "Seq Scan on orders" in (tmp_path / "q1_day_before.txt").read_text()
    assert "Index Only Scan using idx_orders_listing" in (tmp_path / "q3_listing_after.txt").read_text()
    assert len(list(tmp_path.glob("*.txt"))) == 11
