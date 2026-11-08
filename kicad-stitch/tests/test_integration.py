"""Real KiCad 10 tests; opt in with KICAD_STITCH_INTEGRATION=1.

Flatpak tests use a workspace scratch directory because its /tmp is private.
"""
import json
import os
from pathlib import Path
import shlex
import tempfile

import pytest
from shapely.geometry import Point

from kicad_stitch.backend import BackendError, KiCad, drc_issues, fingerprint, run
from kicad_stitch.cli import main
from kicad_stitch.geometry import decode
from kicad_stitch.model import Settings
from kicad_stitch.workflow import apply_review, restore_backup


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


def test_native_discovery_and_worker_with_real_kicad_launchers(native_board):
    """Exercise native discovery against actual bindings via POSIX launchers.

    The CI/development machine may have only Flatpak KiCad. These launchers expose
    its real CLI and Python as a native-style installation beside each other;
    the host uv interpreter still has no pcbnew.
    """
    source, installed = native_board
    if os.name != "posix" or installed.runtime != "flatpak":
        pytest.skip("Requires the POSIX Flatpak fixture for real KiCad launchers")
    directory = source.parent / "native-bin"
    directory.mkdir()
    for name, command in (("kicad-cli", installed.cli), ("python3", installed.python)):
        launcher = directory / name
        launcher.write_text("#!/bin/sh\nexec " + shlex.join(command) + ' "$@"\n')
        launcher.chmod(0o755)
    backend = KiCad("native", cli=str(directory / "kicad-cli"))
    assert backend.check().startswith("10.")
    assert backend.python == [str(directory / "python3")]
    snapshot = backend.snapshot(source, "GND")
    assert snapshot["version"] == installed.check()
    assert decode(snapshot["outline"]).area == pytest.approx(1164)


def test_ground_stitches_make_legal_antipads_in_internal_power_plane(native_board):
    source, backend = native_board
    backend.command([*backend.python, str(Path(__file__).with_name("make_board.py").resolve()),
                     str(source.parent), "--power-plane"])
    original = fingerprint(source)
    output = source.with_name("power-plane-stitched.kicad_pcb")
    result, final, before, after = run(source, Settings(), backend, output=output)
    assert result.validation["status"] == "verified"
    assert not result.validation["blocking_issues"]
    assert result.candidates
    power = decode([poly for obstacle in final["obstacles"]
                    if obstacle["kind"] == "zone" and obstacle["net"] == "+3V3"
                    for poly in obstacle["polygons"]])
    assert power.area > 500
    for via in result.candidates:
        assert power.distance(Point(via.x, via.y)) >= 0.49
    assert output.is_file()
    assert fingerprint(source) == original


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


def test_changed_ratsnest_representative_does_not_block_existing_usb_error(native_board, monkeypatch):
    source, backend = native_board
    backend.command([*backend.python, str(Path(__file__).with_name("make_board.py").resolve()),
                     str(source.parent), "--disconnected-signal"])
    original = fingerprint(source)
    native_drc = backend.drc
    changed_endpoints = []

    def drc_with_changed_endpoint(board, report):
        data = native_drc(board, report)
        if board.parent.name != "proposed":
            return data
        groups = backend.worker("connectivity", board, nets=["/USB_D_P"])
        components = groups["nets"]["/USB_D_P"]
        assert len(components) == 2
        assert all(len(component) == 3 for component in components)
        # Emulate the observed native endpoint re-selection, with the actual
        # KiCad component database proving the board's USB connectivity is intact.
        for missing in data["unconnected_items"]:
            if len(missing.get("items", [])) != 2:
                continue
            a = missing["items"][0]
            if groups["item_nets"].get(a["uuid"]) != "/USB_D_P":
                continue
            component = next(c for c in components if a["uuid"] in c)
            a["uuid"] = next(uid for uid in component if uid != a["uuid"])
            changed_endpoints.append(a["uuid"])
        return data

    monkeypatch.setattr(backend, "drc", drc_with_changed_endpoint)
    output = source.with_name("existing-usb-error-stitched.kicad_pcb")
    result, _, before, after = run(source, Settings(), backend, output=output)
    assert changed_endpoints
    assert before["unconnected_items"]
    assert result.validation["status"] == "verified"
    assert result.validation["unchanged_connectivity_issues"]
    assert result.validation["new_issues"]  # Full raw comparison remains auditable.
    assert not result.validation["blocking_issues"]
    assert not result.validation["rejected_candidates"]
    assert output.is_file()
    assert result.candidates
    assert fingerprint(source) == original


def test_real_connectivity_split_blocks_even_with_same_error_count(native_board, monkeypatch):
    source, backend = native_board
    backend.command([*backend.python, str(Path(__file__).with_name("make_board.py").resolve()),
                     str(source.parent), "--disconnected-signal"])
    original = fingerprint(source)
    script = source.with_name("split_usb.py")
    script.write_text('''import sys
import pcbnew as p
b = p.LoadBoard(sys.argv[1])
def pt(x, y):
    return p.VECTOR2I(p.FromMM(x), p.FromMM(y))
usb = b.GetNetsByName()["/USB_D_P"]
# Break A--B while joining B to the previously separate C--D component.
# The final number of disconnected components is still two.
for t in b.GetTracks():
    if isinstance(t, p.PCB_VIA):
        continue
    if t.GetNetname() == "/USB_D_P" and t.GetStart() == pt(6, 22):
        t.SetEnd(pt(8, 22))
for x in (10, 25):
    v = p.PCB_VIA(b)
    v.SetPosition(pt(x, 22))
    v.SetWidth(p.FromMM(0.6))
    v.SetDrill(p.FromMM(0.3))
    v.SetViaType(p.VIATYPE_THROUGH)
    v.SetLayerPair(p.F_Cu, p.B_Cu)
    v.SetNet(usb)
    b.Add(v)
t = p.PCB_TRACK(b)
t.SetStart(pt(10, 22))
t.SetEnd(pt(25, 22))
t.SetWidth(p.FromMM(0.2))
t.SetLayer(p.B_Cu)
t.SetNet(usb)
b.Add(t)
p.SaveBoard(sys.argv[1], b)
''')
    native_worker = backend.worker

    def worker_with_real_split(action, board, **kwargs):
        result = native_worker(action, board, **kwargs)
        if action == "place":
            backend.command([*backend.python, str(script), str(board)])
        return result

    monkeypatch.setattr(backend, "worker", worker_with_real_split)
    output = source.with_name("failed-for-inspection.kicad_pcb")
    settings = Settings(perimeter=False, grid=False, fingers=False, auto_pairs=False)
    result, _, before, after = run(source, settings, backend, output=output)
    assert len(before["unconnected_items"]) == len(after["unconnected_items"])
    for report in (before, after):
        usb_errors = [issue for issue in report["unconnected_items"]
                      if any("[/USB_D_P]" in item["description"] for item in issue["items"])]
        assert len(usb_errors) == 1
    assert result.validation["status"] == "failed"
    assert not result.validation["unchanged_connectivity_issues"]
    assert any(issue["type"] == "unconnected_items" for issue in result.validation["blocking_issue_details"])
    # The failed proposal is saved for inspection, never applied to the source.
    assert output.exists() and result.validation["published_board"] == str(output)
    assert fingerprint(source) == original


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


@pytest.mark.parametrize("diameter,drill,severity,allow_warnings", [
    (0.5, 0.3, "warning", True),
    (0.6, 0.4, "warning", True),
    (0.5, 0.3, "warning", False),
    (0.5, 0.3, "error", True),
    (0.5, 0.3, "ignore", True),
])
def test_annular_width_uses_native_severity(native_board, diameter, drill, severity, allow_warnings):
    source, backend = native_board
    project = source.with_suffix(".kicad_pro")
    data = json.loads(project.read_text())
    design = data["board"]["design_settings"]
    design["rules"]["min_via_annular_width"] = 0.16
    design["rule_severities"] = {"annular_width": severity}
    project.write_text(json.dumps(data))
    original = fingerprint(source)
    output = source.with_name("annular-stitched.kicad_pcb")
    settings = Settings(diameter_mm=diameter, drill_mm=drill,
                        allow_annular_width_warnings=allow_warnings,
                        perimeter=False, grid=False, fingers=False, auto_pairs=False)
    result, _, before, after = run(source, settings, backend, output=output)
    retained = severity == "ignore" or (severity == "warning" and allow_warnings)
    advisory = severity == "warning" and allow_warnings
    assert result.validation["status"] == ("verified_with_warnings" if advisory else "verified")
    assert bool(result.candidates) == retained
    assert bool(result.validation["advisory_issues"]) == advisory
    assert not result.validation["blocking_issues"]
    assert bool(result.validation["new_issues"]) == advisory
    assert bool(drc_issues(after) - drc_issues(before)) == advisory
    assert output.is_file()
    assert fingerprint(source) == original
    published = json.loads(output.with_suffix(".kicad_pro").read_text())
    assert published["board"]["design_settings"]["rules"]["min_via_annular_width"] == 0.16
    assert published["board"]["design_settings"]["rule_severities"]["annular_width"] == severity
    if advisory:
        assert any(issue["type"] == "annular_width" and issue["severity"] == "warning"
                   for issue in after["violations"])


def test_cli_publishes_annular_warning_report_with_success(native_board, capsys):
    source, _ = native_board
    project = source.with_suffix(".kicad_pro")
    data = json.loads(project.read_text())
    data["board"]["design_settings"]["rules"]["min_via_annular_width"] = 0.16
    data["board"]["design_settings"]["rule_severities"] = {"annular_width": "warning"}
    project.write_text(json.dumps(data))
    original = fingerprint(source)
    config = source.with_name("stitch.toml")
    config.write_text('''[stitch]
diameter_mm = 0.5
drill_mm = 0.3
perimeter = false
grid = false
fingers = false
auto_pairs = false
''')
    output = source.with_name("cli-stitched.kicad_pcb")
    report = source.with_name("cli-report")
    assert main([str(source), "--config", str(config), "--output", str(output),
                 "--report-dir", str(report)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "verified_with_warnings"
    assert summary["vias"] > 0
    assert summary["advisory_issue_count"] > 0
    plan_report = json.loads((report / "plan.json").read_text())
    assert plan_report["validation"]["new_issues"]
    assert not plan_report["validation"]["blocking_issues"]
    assert (report / "preview.svg").is_file()
    assert output.is_file()
    assert fingerprint(source) == original


def test_cli_default_review_can_be_applied_and_restored(native_board, capsys):
    source, backend = native_board
    original = fingerprint(source)
    report = source.parent / "review"
    assert main([str(source), "--report-dir", str(report)]) == 0
    summary = json.loads(capsys.readouterr().out)
    proposed = report / "board" / source.name
    assert proposed.is_file()
    assert "apply_command" in summary
    assert fingerprint(source) == original
    data = json.loads((report / "plan.json").read_text())
    assert data["validation"]["published_sha256"] == fingerprint(proposed)
    applied = apply_review(report)
    assert source.read_bytes() == proposed.read_bytes()
    snapshot = backend.snapshot(source, "GND")
    assert len(snapshot["existing_vias"]) == summary["vias"]
    for path, checksum in original.items():
        if path != str(source):
            assert fingerprint(source)[path] == checksum
    restore_backup(applied["backup"])
    assert fingerprint(source) == original


def test_cli_in_place_backs_up_before_replacing_native_board(native_board, capsys):
    source, backend = native_board
    original = fingerprint(source)
    report = source.parent / "in-place-review"
    assert main([str(source), "--in-place", "--report-dir", str(report)]) == 0
    summary = json.loads(capsys.readouterr().out)
    application = summary["application"]
    assert application["status"] == "applied"
    assert application["board"] == str(source)
    assert fingerprint(source)[str(source)] != original[str(source)]
    assert (Path(application["backup"]) / source.name).is_file()
    snapshot = backend.snapshot(source, "GND")
    assert len(snapshot["existing_vias"]) == summary["vias"]
    restore_backup(application["backup"])
    assert fingerprint(source) == original


def test_renamed_export_apply_revalidates_preserves_vias_and_can_restore(native_board, capsys):
    source, backend = native_board
    backend.command([*backend.python, str(Path(__file__).with_name("make_board.py").resolve()),
                     str(source.parent), "--disconnected-signal"])
    project = source.with_suffix(".kicad_pro")
    data = json.loads(project.read_text())
    data["board"]["design_settings"]["rules"]["min_via_annular_width"] = 0.16
    data["board"]["design_settings"]["rule_severities"] = {"annular_width": "warning"}
    project.write_text(json.dumps(data))
    original = fingerprint(source)
    output = source.with_name("sample_stitched.kicad_pcb")
    report = source.parent / "renamed-review"
    assert main([str(source), "--output", str(output), "--report-dir", str(report)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "verified_with_warnings"
    assert summary["apply_command"]
    export_hashes = fingerprint(output)
    reviewed = backend.snapshot(output, "GND")
    assert main(["apply", str(report), "--runtime", backend.runtime]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["status"] == "applied"
    assert applied["revalidation"]["status"] == "verified_with_warnings"
    audit_path = Path(applied["revalidation"]["report"])
    audit = json.loads(audit_path.read_text())
    assert audit["validated_basename"] == source.name
    assert audit["advisory_issues"]
    assert not audit["blocking_issues"]
    assert not audit["changed_candidate_uuids"]
    assert (audit_path.parent / "baseline-drc.json").is_file()
    assert (audit_path.parent / "final-drc.json").is_file()
    # No rerun of placement: the actual UUIDs, nets and positions survive apply.
    installed = backend.snapshot(source, "GND")
    via_set = lambda snap: {(v["uuid"], v["net"], tuple(v["at"])) for v in snap["existing_vias"]}
    assert via_set(installed) == via_set(reviewed)
    assert fingerprint(output) == export_hashes
    for path, checksum in original.items():
        if path != str(source):
            assert fingerprint(source)[path] == checksum
    restore_backup(applied["backup"])
    assert fingerprint(source) == original


def test_renamed_apply_rejects_original_context_drc_without_pruning_vias(native_board, monkeypatch):
    source, backend = native_board
    original = fingerprint(source)
    output = source.with_name("sample_stitched.kicad_pcb")
    result, _, _, _ = run(source, Settings(), backend, output=output)
    export_hashes = fingerprint(output)
    report = source.parent / "renamed-review"
    report.mkdir()
    (report / "plan.json").write_text(json.dumps(result.to_dict()))
    native_worker = backend.worker
    def stricter_original_context(action, board, **kwargs):
        response = native_worker(action, board, **kwargs)
        if action == "normalize" and board.parent.name == "proposed":
            # Exercise real KiCad DRC with a stricter original-name context.
            # No production file or reviewed export is modified by this hook.
            board.with_suffix(".kicad_dru").write_text('''(version 1)
(rule "Original-context drill minimum"
  (condition "A.Type == 'Via' && A.NetName == 'GND'")
  (constraint hole_size (min 0.4mm)))
''')
        return response
    monkeypatch.setattr(backend, "worker", stricter_original_context)
    with pytest.raises(BackendError, match="Original-name validation failed"):
        apply_review(report, backend)
    assert fingerprint(source) == original
    assert fingerprint(output) == export_hashes
    assert not (source.parent / ".kicad-stitch-backups").exists()
    audit_path, = (report / "apply-validation").glob("*/validation.json")
    audit = json.loads(audit_path.read_text())
    assert audit["status"] == "failed"
    assert audit["blocking_issues"]
    assert audit["via_count"] == len(result.candidates)
    assert not audit["changed_candidate_uuids"]
    assert not list(source.parent.glob(".kicad-stitch-*.lock"))


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
