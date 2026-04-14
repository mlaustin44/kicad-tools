"""Unit tests for kicad-cli wrapper (mocked subprocess)."""
from __future__ import annotations
import subprocess
from unittest.mock import patch, MagicMock
import pytest
from release_generator.kicad_cli import (
    get_version, check_version, run, KicadCliError, MIN_VERSION, _VERSION_RE
)


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@patch("release_generator.kicad_cli.find_kicad_cli", return_value="/usr/bin/kicad-cli")
@patch("release_generator.kicad_cli.subprocess.run")
def test_version_parses_standard_format(mock_run, _mock_find):
    mock_run.return_value = _FakeCompleted(0, "10.0.0\n", "")
    assert get_version() == (10, 0, 0)


@patch("release_generator.kicad_cli.find_kicad_cli", return_value="/usr/bin/kicad-cli")
@patch("release_generator.kicad_cli.subprocess.run")
def test_version_handles_banner_text(mock_run, _mock_find):
    mock_run.return_value = _FakeCompleted(0, "KiCad 10.0.0-rc1\nCopyright ...", "")
    assert get_version() == (10, 0, 0)


@patch("release_generator.kicad_cli.find_kicad_cli", return_value="/usr/bin/kicad-cli")
@patch("release_generator.kicad_cli.subprocess.run")
def test_version_raises_on_unparseable(mock_run, _mock_find):
    mock_run.return_value = _FakeCompleted(0, "no version here\n", "")
    with pytest.raises(KicadCliError, match="unparseable"):
        get_version()


@patch("release_generator.kicad_cli.find_kicad_cli", return_value="/usr/bin/kicad-cli")
@patch("release_generator.kicad_cli.subprocess.run")
def test_version_translates_timeout(mock_run, _mock_find):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="kicad-cli", timeout=10)
    with pytest.raises(KicadCliError, match="timed out"):
        get_version()


@patch("release_generator.kicad_cli.find_kicad_cli", return_value="/usr/bin/kicad-cli")
@patch("release_generator.kicad_cli.subprocess.run")
def test_run_translates_timeout(mock_run, _mock_find):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="kicad-cli", timeout=60)
    with pytest.raises(KicadCliError, match="timed out"):
        run(["pcb", "export", "gerbers"], timeout=60)


@patch("release_generator.kicad_cli.find_kicad_cli", return_value="/usr/bin/kicad-cli")
@patch("release_generator.kicad_cli.subprocess.run")
def test_run_translates_oserror(mock_run, _mock_find):
    mock_run.side_effect = FileNotFoundError("no such file")
    with pytest.raises(KicadCliError, match="failed to execute"):
        run(["version"])


@patch("release_generator.kicad_cli.find_kicad_cli", return_value="/usr/bin/kicad-cli")
@patch("release_generator.kicad_cli.subprocess.run")
def test_run_captures_stdout_even_when_verbose(mock_run, _mock_find, capsys):
    mock_run.return_value = _FakeCompleted(0, "hello world\n", "stderr line\n")
    res = run(["some", "subcmd"], verbose=True)
    assert res.stdout == "hello world\n"  # caller still gets stdout
    captured = capsys.readouterr().out
    assert "$ /usr/bin/kicad-cli some subcmd" in captured  # command echoed
    assert "stderr line" in captured  # stderr streamed in verbose mode
