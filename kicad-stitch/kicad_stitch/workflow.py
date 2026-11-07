"""Apply an exact reviewed board, with local snapshots and guarded restoration.

Only the source PCB is replaced. Project rules and all other project assets stay
in place. These file operations need no KiCad process or replanning.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import tempfile
from uuid import uuid4

from .backend import fingerprint


VERIFIED = {"verified", "verified_with_warnings"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ensure_closed(board):
    for suffix in (".kicad_pcb", ".kicad_pro"):
        path = board.with_suffix(suffix)
        lock = path.with_name("~" + path.name + ".lck")
        if lock.exists():
            raise ValueError(f"Close the KiCad board/project before replacing it (lock: {lock})")


@contextmanager
def project_lock(board):
    """Serialize this tool's apply/restore operations; KiCad has its own locks."""
    lock = board.with_name(".kicad-stitch-" + board.name + ".lock")
    try:
        stream = lock.open("x")
    except FileExistsError as exc:
        raise ValueError(f"Another apply/restore may be running (lock: {lock})") from exc
    try:
        with stream:
            stream.write(str(os.getpid()) + "\n")
        ensure_closed(board)
        yield
    finally:
        lock.unlink()


def write_new(path, content):
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def assert_fingerprint(board, expected, message):
    if fingerprint(board) != expected:
        raise ValueError(message)


def backup_board(board, expected, installed_hash, *, operation, origin):
    """Finish the restorable snapshot before the atomic replacement begins."""
    root = board.parent / ".kicad-stitch-backups"
    root.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = root / (stamp + "-" + uuid4().hex[:8])
    backup.mkdir()
    for name, wanted in expected.items():
        source = Path(name)
        content = source.read_bytes()
        if digest(content) != wanted:
            raise ValueError("Source changed while creating the backup; nothing was replaced")
        target = backup / source.name
        write_new(target, content)
        shutil.copystat(source, target)
    manifest = {"schema_version": 1, "operation": operation, "source_board": str(board),
                "created_utc": stamp, "source_sha256": expected,
                "installed_board_sha256": installed_hash, "origin": str(origin)}
    write_new(backup / "backup.json", (json.dumps(manifest, indent=2) + "\n").encode())
    return backup


def replace_board(board, content, expected):
    """Keep the old PCB intact until the replacement is complete and rechecked."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".kicad-stitch-", dir=board.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(stat.S_IMODE(board.stat().st_mode))
        ensure_closed(board)
        assert_fingerprint(board, expected, "Source changed before replacement; nothing was replaced")
        os.replace(temporary, board)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def board_record(validation):
    """Accept only complete, canonical source-family hash maps from new reports."""
    board = Path(validation["source_board"])
    expected = validation["source_sha256"]
    family = {str(board.with_suffix(s)) for s in (".kicad_pcb", ".kicad_pro", ".kicad_dru")}
    required = {str(board), str(board.with_suffix(".kicad_pro"))}
    if (not board.is_absolute() or board.suffix != ".kicad_pcb" or board.resolve() != board
            or not isinstance(expected, dict) or not required <= set(expected) <= family):
        raise ValueError("Invalid source board/hash record")
    if any(not isinstance(h, str) or len(h) != 64 for h in expected.values()):
        raise ValueError("Invalid source hashes")
    return board, expected


def receipt(status, board, backup):
    return {"status": status, "board": str(board), "backup": str(backup),
            "restore_command": shlex.join(["kicad-stitch", "restore", str(backup)])}


def apply_review(report):
    """Install exactly the saved, validated bytes when the source is unchanged."""
    report = Path(report).resolve()
    plan_path = report / "plan.json" if report.is_dir() else report
    data = json.loads(plan_path.read_text())
    validation = data["validation"]
    if validation["status"] not in VERIFIED or validation.get("blocking_issues") or validation.get("unconnected_candidate_uuids"):
        raise ValueError("Only a successfully verified stitching review can be applied")
    if not all(k in validation for k in ("source_board", "published_sha256", "baseline_sha256", "validated_basename")):
        raise ValueError("This report predates apply support; generate a new review")
    board, expected = board_record(validation)
    published = validation.get("published_board")
    if not published:
        raise ValueError("Review has no saved board; generate a new review")
    proposed = Path(published)
    # Name-dependent custom rules/text variables must match native validation.
    if validation["validated_basename"] != board.name or proposed.name != board.name:
        raise ValueError("Review was validated under a different board name; generate a review without --output")
    if proposed.resolve() == board:
        raise ValueError("The review board must be separate from the source")
    wanted = validation["published_sha256"]
    actual = fingerprint(proposed)
    if not actual or actual != wanted:
        raise ValueError("Reviewed board/project/rules changed since validation; generate a new review")
    baseline = validation["baseline_sha256"]
    if not isinstance(baseline, dict) or str(board.with_suffix(".kicad_pro")) not in baseline:
        raise ValueError("Review lacks the native baseline project identity; generate a new review")
    for suffix in (".kicad_pro", ".kicad_dru"):
        # KiCad may materialize implicit defaults in scratch .kicad_pro files.
        # Compare against its native baseline context, while the original source
        # must still match its raw pre-run hashes before replacement.
        if wanted.get(str(proposed.with_suffix(suffix))) != baseline.get(str(board.with_suffix(suffix))):
            raise ValueError("Reviewed project/rules differ from the native baseline; generate a new review")
    content = proposed.read_bytes()
    if digest(content) != wanted.get(str(proposed)):
        raise ValueError("Reviewed board changed while reading; generate a new review")
    with project_lock(board):
        assert_fingerprint(board, expected, "Source board/project/rules changed since review; generate a new review")
        backup = backup_board(board, expected, digest(content), operation="apply", origin=plan_path)
        replace_board(board, content, expected)
    return receipt("applied", board, backup)


def restore_backup(backup, *, force=False):
    """Undo apply/restore; retain the replaced board in another restorable backup."""
    backup = Path(backup).resolve()
    manifest_path = backup / "backup.json" if backup.is_dir() else backup
    backup = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported backup format")
    board, original = board_record(manifest)
    # Verify the entire snapshot even though only the PCB is restored.
    content = None
    for name, wanted in original.items():
        saved = (backup / Path(name).name).read_bytes()
        if digest(saved) != wanted:
            raise ValueError("Backup content changed; refusing to restore")
        if name == str(board):
            content = saved
    with project_lock(board):
        current = fingerprint(board)
        if str(board) not in current or str(board.with_suffix(".kicad_pro")) not in current:
            raise ValueError("The original board/project must exist to restore")
        if current == original:
            return {"status": "already_restored", "board": str(board), "backup": str(backup)}
        installed = {**original, str(board): manifest["installed_board_sha256"]}
        if not force and current != installed:
            raise ValueError("Board/project/rules changed after this operation; use --force to preserve current files in a new backup and restore the PCB")
        undo = backup_board(board, current, digest(content), operation="restore", origin=manifest_path)
        replace_board(board, content, current)
    return receipt("restored", board, undo)
