"""Unit tests for BOM CSV reshaping."""
from __future__ import annotations
import csv
import io
import pytest
from release_generator.bom import reshape_bom, _field_name_for_kicad


def _csv_str(rows: list[dict]) -> str:
    buf = io.StringIO()
    if not rows:
        return ""
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def test_groups_by_value_and_concatenates_refs():
    raw = _csv_str([
        {"Reference": "R1", "Value": "10k", "Footprint": "0402"},
        {"Reference": "R2", "Value": "10k", "Footprint": "0402"},
        {"Reference": "R3", "Value": "1k", "Footprint": "0402"},
    ])
    out = reshape_bom(raw, group_by=["Value", "Footprint"],
                     columns=["reference", "value", "footprint", "quantity"])
    rows = list(csv.DictReader(io.StringIO(out)))
    assert len(rows) == 2
    by_val = {r["value"]: r for r in rows}
    assert by_val["10k"]["reference"] == "R1, R2"
    assert by_val["10k"]["quantity"] == "2"
    assert by_val["1k"]["reference"] == "R3"
    assert by_val["1k"]["quantity"] == "1"


def test_missing_field_emits_empty_cells_and_warning(capsys):
    raw = _csv_str([{"Reference": "R1", "Value": "10k"}])
    out = reshape_bom(raw, group_by=["Value"],
                     columns=["reference", "value", "mpn", "manufacturer"])
    rows = list(csv.DictReader(io.StringIO(out)))
    assert rows[0]["mpn"] == ""
    assert rows[0]["manufacturer"] == ""
    captured = capsys.readouterr().out
    assert "mpn" in captured.lower() or "missing" in captured.lower()


def test_qty_is_synthesized_like_quantity():
    # Previously 'Qty' was passed to kicad-cli as a field name and came back empty.
    raw = _csv_str([
        {"Reference": "R1", "Value": "10k"},
        {"Reference": "R2", "Value": "10k"},
    ])
    out = reshape_bom(raw, group_by=["Value"], columns=["reference", "value", "Qty"])
    rows = list(csv.DictReader(io.StringIO(out)))
    assert rows[0]["Qty"] == "2"


def test_field_name_preserves_user_casing_and_spaces():
    # Explicit schematic field names must pass through unchanged; titlecasing
    # broke 'LCSC Part' -> 'Lcsc part' and 'Substition_OK' -> 'Substition_Ok'.
    assert _field_name_for_kicad("LCSC Part") == "LCSC Part"
    assert _field_name_for_kicad("Substition_OK") == "Substition_OK"
    assert _field_name_for_kicad("Voltage_Rating") == "Voltage_Rating"
    # Lowercase conveniences still work.
    assert _field_name_for_kicad("mpn") == "MPN"
    assert _field_name_for_kicad("part_number") == "Part_Number"


def test_sorts_references_naturally():
    raw = _csv_str([
        {"Reference": "R10", "Value": "10k"},
        {"Reference": "R2", "Value": "10k"},
        {"Reference": "R1", "Value": "10k"},
    ])
    out = reshape_bom(raw, group_by=["Value"],
                     columns=["reference", "value", "quantity"])
    rows = list(csv.DictReader(io.StringIO(out)))
    assert rows[0]["reference"] == "R1, R2, R10"
