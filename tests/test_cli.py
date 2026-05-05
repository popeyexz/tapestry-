"""Tests for the Tapestry CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tapestry.cli import main


@pytest.fixture()
def runner():
    return CliRunner(mix_stderr=False)


class TestCLIRoot:
    def test_help(self, runner: CliRunner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Tapestry" in result.output

    def test_version(self, runner: CliRunner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestStoryCLI:
    def test_story_empty(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(main, ["story"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        # Either "No memories" or a story header
        assert "No memories" in result.output or "story" in result.output.lower()


class TestMemoryCLI:
    def test_memory_stats_empty(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            main, ["memory", "stats"], env={"HOME": str(tmp_path)}
        )
        assert result.exit_code == 0
        assert "0" in result.output

    def test_memory_list_empty(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            main, ["memory", "list"], env={"HOME": str(tmp_path)}
        )
        assert result.exit_code == 0

    def test_memory_search_empty(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            main, ["memory", "search", "python"], env={"HOME": str(tmp_path)}
        )
        assert result.exit_code == 0
        assert "No memories" in result.output

    def test_memory_add_fact(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            main,
            ["memory", "add-fact", "User prefers Python"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == 0
        assert "stored" in result.output.lower() or "Fact" in result.output

    def test_memory_clear_with_yes_flag(self, runner: CliRunner, tmp_path: Path):
        # First add something
        runner.invoke(
            main,
            ["memory", "add-fact", "temp fact"],
            env={"HOME": str(tmp_path)},
        )
        result = runner.invoke(
            main,
            ["memory", "clear", "--yes"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output


class TestConnectCLI:
    def test_connect_terminal(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            main,
            ["connect", "terminal"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == 0

    def test_connect_github_no_token(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            main,
            ["connect", "github"],
            env={"HOME": str(tmp_path), "TAPESTRY_GITHUB_TOKEN": ""},
        )
        assert result.exit_code == 0
        # Should show an error status but not crash
        assert "token" in result.output.lower() or "github" in result.output.lower()

    def test_connect_filesystem(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            main,
            ["connect", "filesystem", "--path", str(tmp_path)],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == 0
        assert "filesystem" in result.output.lower()
