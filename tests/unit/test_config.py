"""Unit tests for config loading and validation."""
from __future__ import annotations
import datetime
import textwrap
import pytest
from pathlib import Path
from release_generator.config import load_config, ConfigError


def write_minimal_config(tmp_path: Path, **overrides) -> Path:
    """Write a minimal valid config plus dummy referenced files."""
    (tmp_path / "board.kicad_pcb").touch()
    (tmp_path / "board.kicad_sch").touch()
    (tmp_path / "tb.svg").write_text("<svg/>")
    body = textwrap.dedent(f"""
        [project]
        name = "Test"
        version = "{overrides.get('version', '1.0')}"
        date = "{overrides.get('date', '2026-04-14')}"
        pcb_file = "board.kicad_pcb"
        schematic_file = "board.kicad_sch"

        [titleblock]
        template = "tb.svg"
        company = "ACME"
        drawn_by = "M Test"
        confidentiality = "PROPRIETARY"

        [[revisions]]
        rev = "01"
        ec = "N/A"
        description = "Initial"

        [fab_drawing]
        title = "Fab Drawing"
        page_size = "A4"
        notes = ["Note 1"]

        [assembly_drawing]
        title = "Assembly Drawing"
        page_size = "A4"
        notes = ["Note 1"]
        layers_front = ["F.Fab", "Edge.Cuts"]
        layers_back = ["B.Fab", "Edge.Cuts"]
        include_3d_render = true
        render_view = "{overrides.get('render_view', 'top')}"

        [bom]
        group_by = ["value"]
        columns = ["reference", "value", "quantity"]

        [gerbers]
        layers = "auto"
        subtract_soldermask = false
    """).strip()
    cfg = tmp_path / "release.toml"
    cfg.write_text(body)
    return cfg


def test_loads_minimal_valid_config(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    cfg = load_config(cfg_path)
    assert cfg.project.name == "Test"
    assert cfg.project.version == "1.0"
    assert cfg.project.pcb_file.name == "board.kicad_pcb"
    assert cfg.titleblock.company == "ACME"
    assert len(cfg.revisions) == 1
    assert cfg.gerbers.layers == "auto"


def test_resolves_paths_relative_to_config(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    cfg = load_config(cfg_path)
    assert cfg.project.pcb_file.is_absolute()
    assert cfg.project.pcb_file == (tmp_path / "board.kicad_pcb").resolve()


def test_date_auto_resolves_to_today(tmp_path):
    cfg_path = write_minimal_config(tmp_path, date="auto")
    cfg = load_config(cfg_path)
    assert cfg.project.date == datetime.date.today().isoformat()


def test_rejects_missing_pcb_file(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    (tmp_path / "board.kicad_pcb").unlink()
    with pytest.raises(ConfigError, match="pcb_file"):
        load_config(cfg_path)


def test_rejects_empty_version(tmp_path):
    cfg_path = write_minimal_config(tmp_path, version="")
    with pytest.raises(ConfigError, match="version"):
        load_config(cfg_path)


def test_rejects_invalid_render_view(tmp_path):
    cfg_path = write_minimal_config(tmp_path, render_view="sideways")
    with pytest.raises(ConfigError, match="render_view"):
        load_config(cfg_path)


def test_rejects_zero_revisions(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    text = cfg_path.read_text()
    new_text = text.replace('[[revisions]]\nrev = "01"\nec = "N/A"\ndescription = "Initial"', '')
    assert new_text != text, "test fixture out of sync with template"
    cfg_path.write_text(new_text)
    with pytest.raises(ConfigError, match="revisions"):
        load_config(cfg_path)


def test_rejects_revision_missing_ec_field(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    text = cfg_path.read_text()
    # Remove the ec line from the revision entry
    text = text.replace('ec = "N/A"\n', '')
    assert "ec = " not in text.split("[[revisions]]")[1].split("\n\n")[0], \
        "test fixture out of sync: failed to remove ec line"
    cfg_path.write_text(text)
    with pytest.raises(ConfigError, match="revisions"):
        load_config(cfg_path)


def test_sanitizes_version_for_directory(tmp_path):
    cfg_path = write_minimal_config(tmp_path, version="3.2/../evil")
    cfg = load_config(cfg_path)
    assert "/" not in cfg.release_dir_name
    assert ".." not in cfg.release_dir_name


def test_rejects_version_that_sanitizes_to_non_alnum(tmp_path):
    cfg_path = write_minimal_config(tmp_path, version="..")
    cfg = load_config(cfg_path)
    with pytest.raises(ConfigError, match="no alphanumerics"):
        _ = cfg.release_dir_name


def test_gerbers_layers_explicit_list(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    text = cfg_path.read_text()
    new_text = text.replace('layers = "auto"', 'layers = ["F.Cu", "B.Cu"]')
    assert new_text != text, "test fixture out of sync with template"
    cfg_path.write_text(new_text)
    cfg = load_config(cfg_path)
    assert cfg.gerbers.layers == ["F.Cu", "B.Cu"]
