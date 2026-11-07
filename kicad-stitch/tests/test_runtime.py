"""Runtime discovery regressions, including a real isolated-Python reproduction."""
import json
from pathlib import Path
import subprocess
import sys
import venv

import pytest

from kicad_stitch.backend import BackendError, KiCad, fingerprint, run
from kicad_stitch.model import Settings
from kicad_stitch import runtime
from kicad_stitch.runtime import RuntimeDiscoveryError, discover_python, probe_python, python_candidates


def make_python(directory, *, bindings):
    venv.EnvBuilder(with_pip=False).create(directory)
    executable = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python3")
    if bindings:
        result = subprocess.run([str(executable), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                capture_output=True, text=True, check=True)
        (Path(result.stdout.strip()) / "pcbnew.py").write_text("def Version():\n    return '10.0.7'\n")
    return executable


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX CLI shim; discovery itself supports Windows")
def test_native_finds_bindings_outside_the_isolated_tool_environment(tmp_path, monkeypatch):
    tool_python = make_python(tmp_path / "uv-tool", bindings=False)
    kicad_python = make_python(tmp_path / "native-kicad", bindings=True)
    cli = kicad_python.with_name("kicad-cli")
    cli.write_text("#!/bin/sh\nprintf '%s\\n' '10.0.7'\n")
    cli.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(tool_python))
    # The tool's Python really cannot import pcbnew, while the independently
    # discovered worker interpreter can. Neither environment needs Shapely here.
    failed = subprocess.run([str(tool_python), "-c", runtime.PROBE], capture_output=True, text=True)
    assert failed.returncode != 0
    assert "No module named 'pcbnew'" in failed.stderr
    backend = KiCad("native", cli=str(cli))
    assert backend.check() == "10.0.7"
    assert backend.python == [str(kicad_python)]
    assert json.loads(backend.command([*backend.python, "-c", runtime.PROBE])) == {"version": "10.0.7"}


def test_probe_does_not_import_pcbnew_from_the_board_directory(tmp_path):
    python = make_python(tmp_path / "isolated", bindings=False)
    (tmp_path / "pcbnew.py").write_text("def Version():\n    return '10.0.7'\n")
    result = subprocess.run([str(python), "-c", runtime.PROBE], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "No module named 'pcbnew'" in result.stderr


def test_discovery_tries_import_and_abi_failures_before_compatible_python(monkeypatch):
    monkeypatch.setattr(runtime, "python_candidates", lambda cli: iter(["uv-python", "wrong-abi", "system-python"]))
    tried = []

    def probe(args):
        tried.append(args[0])
        if args[0] == "uv-python":
            raise RuntimeError("Traceback\nModuleNotFoundError: No module named 'pcbnew'")
        if args[0] == "wrong-abi":
            raise RuntimeError("ImportError: _pcbnew: undefined symbol")
        return json.dumps({"version": "10.0.7"})

    assert discover_python("kicad-cli", "10.0.7", probe) == ["system-python"]
    assert tried == ["uv-python", "wrong-abi", "system-python"]


def test_explicit_python_never_silently_falls_back(monkeypatch):
    def no_candidates(cli):
        pytest.fail("An explicit interpreter must not start automatic discovery")
    monkeypatch.setattr(runtime, "python_candidates", no_candidates)
    assert discover_python("kicad-cli", "10.0.7", lambda args: '{"version": "10.0.7"}',
                           explicit="/custom/python") == ["/custom/python"]
    with pytest.raises(RuntimeDiscoveryError, match="Configured --kicad-python"):
        discover_python("kicad-cli", "10.0.7", lambda args: '{"version": "9.0.6"}',
                        explicit="/custom/python")


@pytest.mark.parametrize("version", ["9.0.7", "11.0.0", "10.1.0", None, 10, "garbage"])
def test_wrong_binding_version_is_not_accepted(version):
    with pytest.raises(RuntimeDiscoveryError, match="does not match"):
        probe_python(["python3"], "10.0.7", lambda args: json.dumps({"version": version}))


@pytest.mark.parametrize("response", ["", "not json", "{}", "[]"])
def test_invalid_probe_response_is_not_accepted(response):
    with pytest.raises(RuntimeDiscoveryError, match="valid version"):
        probe_python(["python3"], "10.0.7", lambda args: response)


def test_patch_version_difference_is_compatible():
    assert probe_python(["python3"], "10.0.7", lambda args: '{"version": "10.0.6"}') == "10.0.6"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable symlinks")
def test_python_symlinks_are_not_collapsed_across_venv_paths(tmp_path):
    directory = tmp_path / "bin"
    directory.mkdir()
    for name in ("python3", "python"):
        (directory / name).symlink_to(sys.executable)
    candidates = list(python_candidates(str(directory / "kicad-cli")))
    assert candidates[:2] == [str(directory / "python3"), str(directory / "python")]


def test_auto_switches_both_cli_and_python_to_flatpak(monkeypatch):
    monkeypatch.setattr("kicad_stitch.backend.shutil.which", lambda name: "/bin/" + name)
    monkeypatch.setattr("kicad_stitch.backend.discover_python",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeDiscoveryError("native pcbnew missing")))
    calls = []

    def command(self, args, payload=None, **kwargs):
        calls.append(args)
        return '{"version": "10.0.7"}' if "-c" in args else "10.0.7\n"

    monkeypatch.setattr(KiCad, "command", command)
    backend = KiCad()
    assert backend.check() == "10.0.7"
    assert backend.runtime == "flatpak"
    assert backend.cli[:2] == ["flatpak", "run"]
    assert backend.python[:2] == ["flatpak", "run"]
    assert any("--command=python3" in args and "-c" in args for args in calls)
    count = len(calls)
    assert backend.check() == "10.0.7"
    assert len(calls) == count  # The validated selection is cached.


@pytest.mark.parametrize("mode", ["auto", "native"])
def test_explicit_override_disables_flatpak_fallback(monkeypatch, mode):
    monkeypatch.setattr("kicad_stitch.backend.shutil.which", lambda name: "/bin/" + name)
    monkeypatch.setattr(KiCad, "command", lambda self, *args, **kwargs: "10.0.7\n")
    monkeypatch.setattr("kicad_stitch.backend.discover_python",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeDiscoveryError("explicit python failed")))
    backend = KiCad(mode, python="/explicit/python")
    with pytest.raises(BackendError, match="explicit python failed"):
        backend.check()
    assert backend.runtime == "native"


def test_missing_bindings_fail_before_scratch_fill_or_publication(tmp_path, monkeypatch):
    source = tmp_path / "board.kicad_pcb"
    source.write_text("untouched board")
    source.with_suffix(".kicad_pro").write_text('{"board": {"design_settings": {"rules": {}}}}')
    original = fingerprint(source)
    monkeypatch.setattr(KiCad, "command", lambda self, *args, **kwargs: "10.0.7\n")
    monkeypatch.setattr("kicad_stitch.backend.discover_python",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeDiscoveryError("missing pcbnew")))
    monkeypatch.setattr("kicad_stitch.backend.tempfile.TemporaryDirectory",
                        lambda *args, **kwargs: pytest.fail("Runtime failure must precede scratch creation"))
    output = tmp_path / "stitched.kicad_pcb"
    with pytest.raises(BackendError, match="missing pcbnew"):
        run(source, Settings(), KiCad("native"), output=output)
    assert fingerprint(source) == original
    assert not output.exists()


def test_missing_interpreters_have_actionable_guidance(monkeypatch):
    monkeypatch.setattr(runtime, "python_candidates", lambda cli: iter([]))
    with pytest.raises(RuntimeDiscoveryError, match="--kicad-python.*--runtime flatpak"):
        discover_python("kicad-cli", "10.0.7", lambda args: pytest.fail("No interpreters exist"))


def test_flatpak_does_not_silently_ignore_native_overrides():
    with pytest.raises(ValueError, match="native"):
        KiCad("flatpak", python="/usr/bin/python3")
