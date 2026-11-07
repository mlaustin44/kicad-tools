import json
from pathlib import Path

import pytest

from kicad_stitch.backend import fingerprint
from kicad_stitch.cli import main
from kicad_stitch import workflow


@pytest.fixture
def review(tmp_path):
    root = tmp_path / "project with spaces"
    root.mkdir()
    source = root / "example.kicad_pcb"
    source.write_bytes(b"original PCB\n")
    source.with_suffix(".kicad_pro").write_bytes(b"original project\n")
    source.with_suffix(".kicad_dru").write_bytes(b"original custom rules\n")
    source.with_suffix(".kicad_sch").write_bytes(b"untouched schematic\n")
    report = root / "review"
    proposed = report / "board" / source.name
    proposed.parent.mkdir(parents=True)
    proposed.write_bytes(b"native-validated stitched PCB\n")
    for suffix in (".kicad_pro", ".kicad_dru"):
        proposed.with_suffix(suffix).write_bytes(source.with_suffix(suffix).read_bytes())
    validation = {"status": "verified_with_warnings", "source_board": str(source),
                  "source_sha256": fingerprint(source), "published_board": str(proposed),
                  "baseline_sha256": fingerprint(source),
                  "published_sha256": fingerprint(proposed), "validated_basename": source.name,
                  "blocking_issues": [], "unconnected_candidate_uuids": []}
    (report / "plan.json").write_text(json.dumps({"validation": validation}))
    return source, report, proposed


def test_apply_keeps_project_identity_and_restores_exact_original_bytes(review):
    source, report, proposed = review
    original = fingerprint(source)
    result = workflow.apply_review(report)
    assert result["status"] == "applied"
    assert source.read_bytes() == proposed.read_bytes()
    for path, checksum in original.items():
        if Path(path) != source:
            assert fingerprint(source)[path] == checksum
    assert source.with_suffix(".kicad_sch").read_bytes() == b"untouched schematic\n"
    backup = Path(result["backup"])
    assert backup.parent == source.parent / ".kicad-stitch-backups"
    assert (backup / source.name).read_bytes() == b"original PCB\n"
    assert (backup / source.with_suffix(".kicad_pro").name).is_file()
    assert (backup / source.with_suffix(".kicad_dru").name).is_file()
    restored = workflow.restore_backup(backup)
    assert restored["status"] == "restored"
    assert fingerprint(source) == original
    assert workflow.restore_backup(backup)["status"] == "already_restored"
    # Restore itself is reversible: its receipt points to the displaced PCB.
    workflow.restore_backup(restored["backup"])
    assert source.read_bytes() == proposed.read_bytes()


def test_native_project_normalization_does_not_replace_original_settings(review):
    source, report, proposed = review
    project = source.with_suffix(".kicad_pro")
    original = project.read_bytes()
    normalized = original + b"materialized native defaults\n"
    proposed.with_suffix(".kicad_pro").write_bytes(normalized)
    data = json.loads((report / "plan.json").read_text())
    validation = data["validation"]
    validation["baseline_sha256"][str(project)] = workflow.digest(normalized)
    validation["published_sha256"] = fingerprint(proposed)
    (report / "plan.json").write_text(json.dumps(data))
    workflow.apply_review(report)
    assert source.read_bytes() == proposed.read_bytes()
    assert project.read_bytes() == original


@pytest.mark.parametrize("suffix", [".kicad_pro", ".kicad_dru"])
def test_review_must_match_native_baseline_context(review, suffix):
    source, report, proposed = review
    proposed.with_suffix(suffix).write_bytes(b"different effective rules")
    data = json.loads((report / "plan.json").read_text())
    data["validation"]["published_sha256"] = fingerprint(proposed)
    (report / "plan.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="differ from the native baseline"):
        workflow.apply_review(report)
    assert source.read_bytes() == b"original PCB\n"


@pytest.mark.parametrize("suffix", [".kicad_pcb", ".kicad_pro", ".kicad_dru"])
def test_apply_refuses_source_edits_since_review(review, suffix):
    source, report, _ = review
    source.with_suffix(suffix).write_bytes(b"new user edits")
    before = fingerprint(source)
    with pytest.raises(ValueError, match="Source.*changed since review"):
        workflow.apply_review(report)
    assert fingerprint(source) == before
    assert not (source.parent / ".kicad-stitch-backups").exists()


@pytest.mark.parametrize("suffix", [".kicad_pcb", ".kicad_pro", ".kicad_dru"])
def test_apply_refuses_review_edits_since_validation(review, suffix):
    source, report, proposed = review
    original = fingerprint(source)
    proposed.with_suffix(suffix).write_bytes(b"edited result")
    with pytest.raises(ValueError, match="Reviewed.*changed since validation"):
        workflow.apply_review(report)
    assert fingerprint(source) == original


@pytest.mark.parametrize("present", [True, False])
def test_apply_detects_added_or_removed_custom_rules(review, present):
    source, report, _ = review
    rules = source.with_suffix(".kicad_dru")
    if present:
        rules.unlink()
    else:
        data = json.loads((report / "plan.json").read_text())
        del data["validation"]["source_sha256"][str(rules)]
        del data["validation"]["baseline_sha256"][str(rules)]
        (report / "plan.json").write_text(json.dumps(data))
        # The source gained a rules file that was absent during native validation.
        proposed = Path(data["validation"]["published_board"])
        proposed.with_suffix(".kicad_dru").unlink()
        del data["validation"]["published_sha256"][str(proposed.with_suffix(".kicad_dru"))]
        (report / "plan.json").write_text(json.dumps(data))
    before = fingerprint(source)
    with pytest.raises(ValueError, match="Source.*changed"):
        workflow.apply_review(report)
    assert fingerprint(source) == before


@pytest.mark.parametrize("suffix", [".kicad_pcb", ".kicad_pro"])
def test_apply_and_restore_refuse_open_kicad_projects(review, suffix):
    source, report, _ = review
    result = workflow.apply_review(report)
    lock = source.with_name("~" + source.with_suffix(suffix).name + ".lck")
    lock.write_text("editor lock")
    with pytest.raises(ValueError, match="Close.*KiCad"):
        workflow.restore_backup(result["backup"])
    lock.unlink()
    workflow.restore_backup(result["backup"])
    lock.write_text("editor lock")
    before = fingerprint(source)
    with pytest.raises(ValueError, match="Close.*KiCad"):
        workflow.apply_review(report)
    assert fingerprint(source) == before


def test_tool_lock_prevents_concurrent_apply_and_is_not_removed(review):
    source, report, _ = review
    lock = source.with_name(".kicad-stitch-" + source.name + ".lock")
    lock.write_text("other invocation")
    with pytest.raises(ValueError, match="Another apply/restore"):
        workflow.apply_review(report)
    assert lock.read_text() == "other invocation"


def test_restore_later_edits_requires_force_and_preserves_them(review):
    source, report, _ = review
    result = workflow.apply_review(report)
    source.write_bytes(b"later user layout work\n")
    with pytest.raises(ValueError, match="--force"):
        workflow.restore_backup(result["backup"])
    assert source.read_bytes() == b"later user layout work\n"
    restored = workflow.restore_backup(result["backup"], force=True)
    assert source.read_bytes() == b"original PCB\n"
    undo = Path(restored["backup"])
    assert (undo / source.name).read_bytes() == b"later user layout work\n"
    workflow.restore_backup(undo)
    assert source.read_bytes() == b"later user layout work\n"


def test_tampered_backup_cannot_be_restored(review):
    source, report, _ = review
    result = workflow.apply_review(report)
    backup = Path(result["backup"])
    (backup / source.name).write_bytes(b"changed backup")
    before = fingerprint(source)
    with pytest.raises(ValueError, match="Backup content changed"):
        workflow.restore_backup(backup)
    assert fingerprint(source) == before


def test_atomic_replace_failure_leaves_source_intact_and_backup_available(review, monkeypatch):
    source, report, _ = review
    original = fingerprint(source)
    def fail(*args):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(workflow.os, "replace", fail)
    with pytest.raises(OSError, match="simulated replace failure"):
        workflow.apply_review(report)
    assert fingerprint(source) == original
    backup, = (source.parent / ".kicad-stitch-backups").iterdir()
    assert workflow.restore_backup(backup)["status"] == "already_restored"
    assert not list(source.parent.glob(".kicad-stitch-*.lock"))
    assert not any(p.is_file() for p in source.parent.glob(".kicad-stitch-*"))


def test_backup_write_failure_never_replaces_source(review, monkeypatch):
    source, report, _ = review
    original = fingerprint(source)
    def fail(*args):
        raise OSError("simulated backup write failure")
    monkeypatch.setattr(workflow, "write_new", fail)
    with pytest.raises(OSError, match="simulated backup write failure"):
        workflow.apply_review(report)
    assert fingerprint(source) == original


def test_source_edit_during_backup_is_rechecked_before_replace(review, monkeypatch):
    source, report, _ = review
    native_backup = workflow.backup_board
    def racing_backup(*args, **kwargs):
        result = native_backup(*args, **kwargs)
        source.write_bytes(b"racing edit")
        return result
    monkeypatch.setattr(workflow, "backup_board", racing_backup)
    with pytest.raises(ValueError, match="Source changed before replacement"):
        workflow.apply_review(report)
    assert source.read_bytes() == b"racing edit"


def test_restore_uses_the_bytes_it_verified_even_if_backup_changes(review, monkeypatch):
    source, report, _ = review
    applied = workflow.apply_review(report)
    saved = Path(applied["backup"]) / source.name
    native_read = Path.read_bytes
    reads = []
    def read_changing_backup(path):
        if path == saved:
            reads.append(path)
            if len(reads) > 1:
                return b"unverified later backup edit"
        return native_read(path)
    monkeypatch.setattr(Path, "read_bytes", read_changing_backup)
    workflow.restore_backup(applied["backup"])
    assert source.read_bytes() == b"original PCB\n"


@pytest.mark.parametrize("change,message", [
    ({"status": "failed"}, "successfully verified"),
    ({"published_sha256": None}, "changed since validation"),
    ({"validated_basename": "renamed.kicad_pcb"}, "different board name"),
    ({"published_board": None}, "no saved board"),
])
def test_invalid_reviews_cannot_be_applied(review, change, message):
    source, report, _ = review
    data = json.loads((report / "plan.json").read_text())
    data["validation"].update(change)
    (report / "plan.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match=message):
        workflow.apply_review(report)
    assert source.read_bytes() == b"original PCB\n"


def test_cli_apply_and_restore_print_action_and_backup(review, capsys):
    source, report, proposed = review
    assert main(["apply", str(report)]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["status"] == "applied"
    assert source.read_bytes() == proposed.read_bytes()
    assert main(["restore", applied["backup"]]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["status"] == "restored"
    assert source.read_bytes() == b"original PCB\n"


def test_cli_rejects_legacy_report_without_provenance(review, capsys):
    _, report, _ = review
    data = json.loads((report / "plan.json").read_text())
    del data["validation"]["published_sha256"]
    (report / "plan.json").write_text(json.dumps(data))
    assert main(["apply", str(report)]) == 1
    assert "predates apply support" in capsys.readouterr().err
