"""Real KiCad 10 tests; opt in with KICAD_STITCH_INTEGRATION=1.

Flatpak tests use a workspace scratch directory because its /tmp is private.
"""
import json
import os
from pathlib import Path
import tempfile

import pytest

from kicad_stitch.backend import KiCad, drc_issues, fingerprint, run
from kicad_stitch.geometry import decode
from kicad_stitch.model import Settings


pytestmark = pytest.mark.skipif(os.environ.get("KICAD_STITCH_INTEGRATION") != "1",
                                reason="Set KICAD_STITCH_INTEGRATION=1 with KiCad 10 available")


@pytest.fixture
def native_board():
    backend = KiCad(os.environ.get("KICAD_STITCH_RUNTIME", "auto"))
    backend.check()
    with tempfile.TemporaryDirectory(prefix=".kicad-stitch-test-", dir=Path.cwd()) as tmp:
        root = Path(tmp)
        backend.command([*backend.python, str(Path(__file__).with_name("make_board.py").resolve()), str(root)])
        yield root / "sample.kicad_pcb", backend


def test_recovers_removed_island_without_new_drc_or_source_changes(native_board):
    source, backend = native_board
    original = fingerprint(source)
    output = source.with_name("stitched.kicad_pcb")
    result, exploratory, before, after = run(source, Settings(), backend, output=output)
    assert result.validation["status"] == "verified"
    assert result.validation["new_issues"] == []
    assert result.validation["unconnected_candidate_uuids"] == []
    assert any(c.rule == "island" for c in result.candidates)
    assert len(exploratory["outline"]) == 1
    assert len(exploratory["outline"][0]["holes"]) == 1
    assert decode(exploratory["outline"]).area == pytest.approx(1164)
    assert any(c.rule == "perimeter" and 16 <= c.x <= 24 and 11 <= c.y <= 19
               for c in result.candidates)
    assert output.is_file() and output.with_suffix(".kicad_pro").is_file()
    assert fingerprint(source) == original
    assert not drc_issues(after) - drc_issues(before)
    final = backend.snapshot(output, "GND")
    assert decode(final["ground"]["F.Cu"]).area > 900
    assert final["version"].startswith("10.")
    # The published board keeps the original island-removal policy.
    assert '(island_removal_mode 0)' in output.read_text()  # KiCad ALWAYS = 0
    assert '(island_removal_mode 1)' not in output.read_text()
    assert len(result.candidates) == len(final["existing_vias"])


def test_custom_rules_reject_candidates_and_preserve_source(native_board):
    source, backend = native_board
    source.with_suffix(".kicad_dru").write_text('''(version 1)
(rule "Larger GND via drills"
  (condition "A.Type == 'Via' && A.NetName == 'GND'")
  (constraint hole_size (min 0.4mm)))
''')
    original = fingerprint(source)
    output = source.with_name("custom-stitched.kicad_pcb")
    result, _, _, _ = run(source, Settings(), backend, output=output)
    assert result.validation["status"] == "verified"
    assert len(result.validation["rejected_candidates"]) > 0
    assert len(result.candidates) == 0
    assert result.validation["validation_iterations"] == 2
    assert fingerprint(source) == original
    assert output.with_suffix(".kicad_dru").read_text() == source.with_suffix(".kicad_dru").read_text()


def test_repeated_run_is_idempotent_and_existing_output_is_protected(native_board):
    source, backend = native_board
    output = source.with_name("stitched.kicad_pcb")
    first, _, _, _ = run(source, Settings(), backend, output=output)
    assert first.candidates
    second, _, _, _ = run(output, Settings(), backend)
    assert second.validation["status"] == "verified"
    assert not second.candidates
    with pytest.raises(ValueError, match="new .kicad_pcb"):
        run(source, Settings(), backend, output=output)


def test_real_board_from_environment():
    """Optional read-only smoke test against a user's real design."""
    value = os.environ.get("KICAD_STITCH_TEST_BOARD")
    if not value:
        pytest.skip("Set KICAD_STITCH_TEST_BOARD for a real-project smoke test")
    source = Path(value).resolve()
    original = fingerprint(source)
    # Real legacy fixtures may have much larger fabrication minima than the
    # package defaults. Choose legal sizes for this smoke test explicitly.
    rules = json.loads(source.with_suffix(".kicad_pro").read_text())["board"]["design_settings"]["rules"]
    drill = max(0.3, rules.get("min_through_hole_diameter", 0))
    diameter = max(0.6, rules.get("min_via_diameter", 0),
                   drill + 2 * max(0.15, rules.get("min_via_annular_width", 0)))
    result, _, _, _ = run(source, Settings(diameter_mm=diameter, drill_mm=drill), KiCad())
    assert result.validation["status"] == "verified"
    assert fingerprint(source) == original
