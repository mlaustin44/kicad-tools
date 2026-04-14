"""TOML config loader and validator."""
from __future__ import annotations
import datetime
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union


class ConfigError(ValueError):
    """Raised on any config validation failure."""


@dataclass
class ProjectConfig:
    name: str
    version: str
    date: str
    pcb_file: Path
    schematic_file: Path


@dataclass
class TitleblockConfig:
    template: Path
    company: str
    drawn_by: str
    confidentiality: str
    logo_file: Path | None = None


@dataclass
class RevisionEntry:
    rev: str
    ec: str
    description: str


@dataclass
class SchematicConfig:
    extra_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class FabDrawingConfig:
    title: str
    page_size: str
    notes: list[str]
    include_3d_render: bool
    render_view: str
    template: Path | None = None


@dataclass
class AssemblyDrawingConfig:
    title: str
    page_size: str
    notes: list[str]
    layers_front: list[str]
    layers_back: list[str]
    template: Path | None = None


@dataclass
class BomConfig:
    group_by: list[str]
    columns: list[str]


@dataclass
class GerbersConfig:
    layers: Union[str, list[str]]  # "auto" or explicit list
    subtract_soldermask: bool


@dataclass
class Config:
    project: ProjectConfig
    titleblock: TitleblockConfig
    revisions: list[RevisionEntry]
    schematic: SchematicConfig
    fab_drawing: FabDrawingConfig
    assembly_drawing: AssemblyDrawingConfig
    bom: BomConfig
    gerbers: GerbersConfig
    config_dir: Path

    @property
    def release_dir_name(self) -> str:
        """Sanitized version string safe for use as a directory name."""
        sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", self.project.version)
        # Collapse runs of dots to a single dot so ".." can't appear.
        sanitized = re.sub(r"\.{2,}", ".", sanitized)
        if not any(c.isalnum() for c in sanitized):
            raise ConfigError(
                f"[project] version {self.project.version!r} sanitizes to "
                f"a directory name {sanitized!r} with no alphanumerics; "
                f"use a version string with at least one letter or digit"
            )
        return sanitized


def _require(d: dict, section: str, key: str):
    if key not in d:
        raise ConfigError(f"[{section}] missing required key '{key}'")
    return d[key]


def _resolve_path(base: Path, rel: str, must_exist: bool, label: str) -> Path:
    p = (base / rel).resolve()
    if must_exist and not p.exists():
        raise ConfigError(f"{label} not found: {p}")
    return p


def load_config(config_path: str | Path) -> Config:
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    base = config_path.parent

    # [project]
    proj_raw = _require(raw, "root", "project")
    version = str(_require(proj_raw, "project", "version"))
    if not version.strip():
        raise ConfigError("[project] version must be non-empty")
    date = str(_require(proj_raw, "project", "date"))
    if date == "auto":
        date = datetime.date.today().isoformat()
    project = ProjectConfig(
        name=str(_require(proj_raw, "project", "name")),
        version=version,
        date=date,
        pcb_file=_resolve_path(base, _require(proj_raw, "project", "pcb_file"),
                               must_exist=True, label="[project] pcb_file"),
        schematic_file=_resolve_path(base, _require(proj_raw, "project", "schematic_file"),
                                     must_exist=True, label="[project] schematic_file"),
    )

    # [titleblock]
    tb_raw = _require(raw, "root", "titleblock")
    titleblock = TitleblockConfig(
        template=_resolve_path(base, _require(tb_raw, "titleblock", "template"),
                               must_exist=True, label="[titleblock] template"),
        company=str(_require(tb_raw, "titleblock", "company")),
        drawn_by=str(_require(tb_raw, "titleblock", "drawn_by")),
        confidentiality=str(_require(tb_raw, "titleblock", "confidentiality")),
        logo_file=(_resolve_path(base, tb_raw["logo_file"], must_exist=True,
                                 label="[titleblock] logo_file")
                   if "logo_file" in tb_raw else None),
    )

    # [[revisions]]
    revs_raw = raw.get("revisions", [])
    if not revs_raw:
        raise ConfigError("at least one [[revisions]] entry is required")
    revisions = []
    for i, r in enumerate(revs_raw):
        section = f"revisions[{i}]"
        revisions.append(RevisionEntry(
            rev=str(_require(r, section, "rev")),
            ec=str(_require(r, section, "ec")),
            description=str(_require(r, section, "description")),
        ))

    # [schematic] (optional)
    sch_raw = raw.get("schematic", {})
    schematic = SchematicConfig(
        extra_vars={str(k): str(v) for k, v in sch_raw.get("extra_vars", {}).items()},
    )

    # [fab_drawing]
    fab_raw = _require(raw, "root", "fab_drawing")
    render_view = str(fab_raw.get("render_view", "top"))
    if render_view not in ("top", "bottom", "both"):
        raise ConfigError(f"[fab_drawing] render_view must be one of "
                          f"top/bottom/both, got '{render_view}'")
    fab = FabDrawingConfig(
        title=str(_require(fab_raw, "fab_drawing", "title")),
        page_size=str(_require(fab_raw, "fab_drawing", "page_size")),
        notes=[str(n) for n in fab_raw.get("notes", [])],
        include_3d_render=bool(fab_raw.get("include_3d_render", False)),
        render_view=render_view,
        template=(_resolve_path(base, fab_raw["template"], must_exist=True,
                                label="[fab_drawing] template")
                  if "template" in fab_raw else None),
    )

    # [assembly_drawing]
    asm_raw = _require(raw, "root", "assembly_drawing")
    asm = AssemblyDrawingConfig(
        title=str(_require(asm_raw, "assembly_drawing", "title")),
        page_size=str(_require(asm_raw, "assembly_drawing", "page_size")),
        notes=[str(n) for n in asm_raw.get("notes", [])],
        layers_front=[str(l) for l in asm_raw.get("layers_front", [])],
        layers_back=[str(l) for l in asm_raw.get("layers_back", [])],
        template=(_resolve_path(base, asm_raw["template"], must_exist=True,
                                label="[assembly_drawing] template")
                  if "template" in asm_raw else None),
    )

    # [bom]
    bom_raw = _require(raw, "root", "bom")
    bom = BomConfig(
        group_by=[str(g) for g in bom_raw.get("group_by", [])],
        columns=[str(c) for c in bom_raw.get("columns", [])],
    )

    # [gerbers]
    gb_raw = _require(raw, "root", "gerbers")
    gb_layers = gb_raw.get("layers", "auto")
    if not (gb_layers == "auto" or
            (isinstance(gb_layers, list) and all(isinstance(x, str) for x in gb_layers))):
        raise ConfigError("[gerbers] layers must be \"auto\" or a list of strings")
    gerbers = GerbersConfig(
        layers=gb_layers,
        subtract_soldermask=bool(gb_raw.get("subtract_soldermask", False)),
    )

    return Config(
        project=project, titleblock=titleblock, revisions=revisions,
        schematic=schematic, fab_drawing=fab, assembly_drawing=asm,
        bom=bom, gerbers=gerbers, config_dir=base,
    )
