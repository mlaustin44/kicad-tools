"""Shared helpers for integration tests."""
from __future__ import annotations
import shutil
from pathlib import Path


def _default_tables(pcb_name: str, sch_name: str) -> dict[str, dict]:
    return {
        "project": {
            "name": "Test",
            "version": "T1",
            "date": "auto",
            "pcb_file": pcb_name,
            "schematic_file": sch_name,
        },
        "titleblock": {
            "template": "tb.svg",
            "company": "ACME",
            "drawn_by": "M Test",
            "confidentiality": "PROPRIETARY",
        },
        "fab_drawing": {
            "title": "Fab Drawing",
            "page_size": "A4",
            "notes": [],
            "include_3d_render": False,
            "render_view": "top",
        },
        "assembly_drawing": {
            "title": "Assembly Drawing",
            "page_size": "A4",
            "notes": [],
            "layers_front": ["F.Fab", "Edge.Cuts"],
            "layers_back": ["B.Fab", "Edge.Cuts"],
        },
        "bom": {
            "group_by": ["value"],
            "columns": ["reference", "value", "quantity"],
        },
        "gerbers": {
            "layers": "auto",
            "subtract_soldermask": False,
        },
    }


def _toml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(_toml_scalar(x) for x in v) + "]"
    raise TypeError(f"unsupported TOML value: {type(v)}")


def _serialize_tables(tables: dict[str, dict], revisions: list[dict]) -> str:
    out_lines: list[str] = []
    for section, body in tables.items():
        out_lines.append(f"[{section}]")
        for k, v in body.items():
            out_lines.append(f"{k} = {_toml_scalar(v)}")
        out_lines.append("")
    for rev in revisions:
        out_lines.append("[[revisions]]")
        for k, v in rev.items():
            out_lines.append(f"{k} = {_toml_scalar(v)}")
        out_lines.append("")
    return "\n".join(out_lines)


def write_test_config(
    workdir: Path,
    kicad_project: Path,
    *,
    tables: dict[str, dict] | None = None,
    revisions: list[dict] | None = None,
) -> Path:
    """Copy the KiCad project tree into workdir/project/ and write a release.toml.

    `tables` merges into the default config (section-by-section, keys in `tables`
    override defaults). `revisions` replaces the default single-entry revisions list.
    Returns the absolute path to the written release.toml.
    """
    proj_copy = workdir / "project"
    shutil.copytree(kicad_project, proj_copy)
    pro = next(proj_copy.glob("*.kicad_pro"))
    sch = proj_copy / f"{pro.stem}.kicad_sch"
    pcb = proj_copy / f"{pro.stem}.kicad_pcb"
    assert sch.exists(), f"expected {sch}"
    assert pcb.exists(), f"expected {pcb}"

    (proj_copy / "tb.svg").write_text("<svg/>")

    default = _default_tables(pcb.name, sch.name)
    if tables:
        for section, overrides in tables.items():
            default.setdefault(section, {}).update(overrides)

    revs = revisions if revisions is not None else [
        {"rev": "01", "ec": "N/A", "description": "Initial"}
    ]

    toml_text = _serialize_tables(default, revs)
    cfg_path = proj_copy / "release.toml"
    cfg_path.write_text(toml_text)
    return cfg_path
