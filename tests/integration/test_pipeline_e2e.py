"""End-to-end pipeline test against the real KiCad project."""
from __future__ import annotations
from pathlib import Path
import shutil
from release_generator.__main__ import main
from ._helpers import write_test_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "titleblock_a4.svg"


def test_full_pipeline_against_real_project(kicad_project, tmp_path, capsys):
    cfg_path = write_test_config(tmp_path, kicad_project)
    proj_dir = cfg_path.parent
    shutil.copy(TEMPLATE, proj_dir / "tb.svg")
    # include_3d_render = False is the helper default; that keeps the test snappy.

    rc = main(["--config", str(cfg_path)])
    assert rc == 0

    out = proj_dir / "releases" / "T1"
    assert (out / "schematic.pdf").exists()
    assert (out / "bom.csv").exists()
    assert (out / "pick-and-place.csv").exists()
    assert (out / "fab-drawing.pdf").exists()
    assert (out / "assembly-drawing.pdf").exists()
    # Gerbers: job file is reliable; at least one .drl
    assert list((out / "gerbers").glob("*.gbrjob"))
    assert list((out / "gerbers").glob("*.drl"))

    captured = capsys.readouterr().out
    assert "Summary" in captured
