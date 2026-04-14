"""BOM generation: kicad-cli sch export bom + post-process to config columns/grouping.

The kicad-cli output uses CamelCase column names (Reference, Value, Footprint, Datasheet,
plus user fields). Our config uses lowercase-with-underscores. We map between them
case-insensitively.
"""
from __future__ import annotations
import csv
import io
import re
from pathlib import Path
from .config import Config
from .kicad_cli import run as kicad_run
from .utils import output_dir_for


_NUM_RE = re.compile(r"(\d+)")


def _natural_key(s: str):
    """Sort 'R1' < 'R2' < 'R10' instead of 'R1' < 'R10' < 'R2'."""
    parts = _NUM_RE.split(s)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def _normalize(s: str) -> str:
    return s.lower().replace(" ", "_")


def _resolve_column(column: str, available_keys: list[str]) -> str | None:
    """Find the case-insensitive matching column in the kicad-cli output."""
    target = _normalize(column)
    for k in available_keys:
        if _normalize(k) == target:
            return k
    return None


def reshape_bom(raw_csv: str, group_by: list[str], columns: list[str]) -> str:
    """Group raw kicad-cli BOM CSV by `group_by`, output columns specified by `columns`.

    Returns the reshaped CSV as a string. Prints a warning to stdout for each
    requested column not found in the source.
    """
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows = list(reader)
    fieldnames = reader.fieldnames or []

    # Resolve group_by columns (must exist or grouping fails)
    grp_keys = []
    for g in group_by:
        actual = _resolve_column(g, fieldnames)
        if actual is None:
            raise ValueError(f"group_by column '{g}' not found in BOM. "
                             f"Available: {fieldnames}")
        grp_keys.append(actual)

    # Reference column (always required for output if requested)
    ref_key = _resolve_column("reference", fieldnames)

    # Group rows
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = tuple(row.get(k, "") for k in grp_keys)
        groups.setdefault(key, []).append(row)

    # Warn once per missing column
    missing = []
    column_resolutions: list[tuple[str, str | None]] = []
    for col in columns:
        if col.lower() == "quantity":
            column_resolutions.append((col, None))  # synthesized
            continue
        actual = _resolve_column(col, fieldnames)
        column_resolutions.append((col, actual))
        if actual is None:
            missing.append(col)
    if missing:
        print(f"warning: BOM columns not found in source, will be empty: {missing}")

    # Build output rows
    out_rows: list[dict] = []
    for _, members in groups.items():
        # Concatenate refs naturally sorted
        if ref_key:
            refs = sorted([m.get(ref_key, "") for m in members if m.get(ref_key)],
                          key=_natural_key)
            ref_str = ", ".join(refs)
        else:
            ref_str = ""
        first = members[0]
        out_row: dict = {}
        for col, actual in column_resolutions:
            if col.lower() == "reference":
                out_row[col] = ref_str
            elif col.lower() == "quantity":
                out_row[col] = str(len(members))
            elif actual:
                out_row[col] = first.get(actual, "")
            else:
                out_row[col] = ""
        out_rows.append(out_row)

    # Warn about columns that exist in source but are entirely empty (e.g. MPN
    # requested but no symbol populates it). Distinct from `missing` above,
    # which is for columns absent from the CSV header.
    empty_cols: list[str] = []
    for col, actual in column_resolutions:
        if actual is None or col.lower() in {"reference", "quantity"}:
            continue
        if all(not r.get(col) for r in out_rows):
            empty_cols.append(col)
    if empty_cols:
        print(f"warning: BOM columns present but all rows empty: {empty_cols}")

    # Sort output by first ref for stability
    out_rows.sort(key=lambda r: _natural_key(r.get("reference", "").split(",")[0]))

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(out_rows)
    return buf.getvalue()


def _titlecase_field(name: str) -> str:
    """Convert 'mpn' -> 'MPN' or 'part_number' -> 'Part_Number' for kicad-cli --fields."""
    if name.lower() in {"mpn", "dnp"}:
        return name.upper()
    return "_".join(p.capitalize() for p in name.replace("-", "_").split("_"))


def generate_bom(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    """Run kicad-cli sch export bom, then reshape per config.

    We pass explicit --fields and --labels so the CSV header column names are stable
    and predictable (KiCad 10 otherwise relabels e.g. Reference -> Refs by default).
    """
    out_dir = output_dir_for(cfg)
    raw_csv_path = out_dir / ".scratch" / "bom_raw.csv"
    raw_csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the union of fields we need: always Reference, plus group_by, plus columns
    # (excluding synthesized 'quantity' / 'reference').
    requested: list[str] = ["Reference"]
    for src in list(cfg.bom.group_by) + list(cfg.bom.columns):
        if src.lower() in {"reference", "quantity"}:
            continue
        pretty = _titlecase_field(src)
        if pretty not in requested:
            requested.append(pretty)

    fields_arg = ",".join(requested)
    args = ["sch", "export", "bom", str(cfg.project.schematic_file),
            "-o", str(raw_csv_path),
            "--fields", fields_arg,
            "--labels", fields_arg]
    kicad_run(args, verbose=verbose)
    raw = raw_csv_path.read_text(encoding="utf-8")
    reshaped = reshape_bom(raw, group_by=cfg.bom.group_by, columns=cfg.bom.columns)
    final_path = out_dir / "bom.csv"
    final_path.write_text(reshaped, encoding="utf-8")
    return final_path, []
