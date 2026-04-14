"""Integration tests for kicad-cli wrapper."""
from __future__ import annotations
import pytest
from release_generator.kicad_cli import (
    find_kicad_cli, get_version, check_version, run, KicadCliError, MIN_VERSION
)


def test_finds_kicad_cli():
    path = find_kicad_cli()
    assert path.endswith("kicad-cli")


def test_version_is_at_least_minimum():
    v = get_version()
    assert v >= MIN_VERSION
    check_version()  # should not raise


def test_run_succeeds_with_version():
    res = run(["version"], verbose=False, timeout=10)
    assert res.returncode == 0
    assert res.stdout.strip()


def test_run_raises_on_bogus_subcommand():
    with pytest.raises(KicadCliError):
        run(["nonexistent-subcommand"], verbose=False, timeout=10)
