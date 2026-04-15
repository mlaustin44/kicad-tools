"""End-to-end pipeline test against the real KiCad project."""
from __future__ import annotations
from pathlib import Path
import shutil
from release_generator.__main__ import main
from ._helpers import write_test_config

REPO_ROOT = Path(__file__).resolve().parents[2]
FAB_TEMPLATE = REPO_ROOT / "templates" / "titleblock_fab_a4.svg"
ASM_TEMPLATE = REPO_ROOT / "templates" / "titleblock_assembly_a4.svg"


def test_full_pipeline_against_real_project(kicad_project, tmp_path, capsys):
    cfg_path = write_test_config(
        tmp_path, kicad_project,
        tables={
            "fab_drawing": {"template": "tb_fab.svg"},
            "assembly_drawing": {"template": "tb_asm.svg"},
        },
    )
    proj_dir = cfg_path.parent
    shutil.copy(FAB_TEMPLATE, proj_dir / "tb_fab.svg")
    shutil.copy(ASM_TEMPLATE, proj_dir / "tb_asm.svg")

    rc = main(["--config", str(cfg_path)])
    assert rc == 0

    out = proj_dir / "releases" / "T1"
    prefix = "test-board_T1"
    assert (out / f"{prefix}_SCHEMATICS.pdf").exists()
    assert (out / f"{prefix}_BOM.csv").exists()
    assert (out / f"{prefix}_PICK_AND_PLACE.csv").exists()
    assert (out / f"{prefix}_FABRICATION_DRAWING.pdf").exists()
    assert (out / f"{prefix}_ASSEMBLY_DRAWING.pdf").exists()
    assert (out / f"{prefix}_DRILL.drl").exists()
    # Gerbers: job file is reliable; at least one .drl
    assert list((out / "gerbers").glob("*.gbrjob"))
    assert list((out / "gerbers").glob("*.drl"))

    captured = capsys.readouterr().out
    assert "Summary" in captured
