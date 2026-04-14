"""Shared pytest fixtures and markers."""
from __future__ import annotations
import os
import pytest
from pathlib import Path

KICAD_TEST_PROJECT_ENV = "KICAD_TEST_PROJECT"
DEFAULT_TEST_PROJECT = Path("/home/mlaustin/electronics/kicad_designs/example_pcb")


@pytest.fixture
def kicad_project() -> Path:
    """Path to a real KiCad project for integration tests."""
    raw = os.environ.get(KICAD_TEST_PROJECT_ENV)
    path = Path(raw) if raw else DEFAULT_TEST_PROJECT
    if not path.exists():
        pytest.skip(f"KiCad test project not available at {path}; "
                    f"set {KICAD_TEST_PROJECT_ENV} env var")
    return path
