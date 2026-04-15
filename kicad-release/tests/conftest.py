"""Shared pytest fixtures and markers."""
from __future__ import annotations
import os
import pytest
from pathlib import Path

KICAD_TEST_PROJECT_ENV = "KICAD_TEST_PROJECT"


@pytest.fixture
def kicad_project() -> Path:
    """Path to a real KiCad project for integration tests."""
    raw = os.environ.get(KICAD_TEST_PROJECT_ENV)
    if not raw:
        pytest.skip(
            f"integration tests require a real KiCad project; "
            f"set the {KICAD_TEST_PROJECT_ENV} env var to a project directory"
        )
    path = Path(raw)
    if not path.exists():
        pytest.skip(f"KICAD_TEST_PROJECT path does not exist: {path}")
    return path
