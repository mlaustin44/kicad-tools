"""Locate and probe KiCad's Python without importing it into the host package."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sys


PROBE = """import sys
if sys.path and sys.path[0] == '':
    sys.path.pop(0)
import json
import pcbnew
print(json.dumps({'version': pcbnew.Version()}))
"""


class RuntimeDiscoveryError(RuntimeError):
    pass


def python_candidates(cli):
    """Prefer the CLI installation and system Python over uv's isolated Python.

    Do not resolve Python symlinks for deduplication: a venv executable and the
    system executable can resolve to the same binary but have different sys.path.
    """
    cli_path = Path(shutil.which(cli) or cli).expanduser().resolve()
    directory = cli_path.parent
    candidates = [directory / name for name in ("python3", "python", "python.exe", "python3.exe")]
    candidates += [directory.parent / "Frameworks/Python.framework/Versions/Current/bin/python3",
                   Path("/usr/bin/python3"), Path("/usr/local/bin/python3")]
    for name in ("python3", "python"):
        executable = shutil.which(name)
        if executable:
            candidates.append(Path(executable))
    for executable in (getattr(sys, "_base_executable", None), sys.executable):
        if executable:
            candidates.append(Path(executable))
    seen = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key not in seen and candidate.is_file() and os.access(candidate, os.X_OK):
            seen.add(key)
            yield str(candidate)


def compatible_version(expected, actual):
    expected_pair = re.match(r"^(\d+)\.(\d+)(?:\.|$)", expected)
    actual_pair = re.match(r"^(\d+)\.(\d+)(?:\.|$)", actual)
    return bool(expected_pair and actual_pair and expected_pair.groups() == actual_pair.groups())


def probe_python(command, expected_version, run):
    response = run([*command, "-c", PROBE])
    try:
        version = json.loads(response)["version"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeDiscoveryError("pcbnew probe did not return a valid version") from exc
    if not isinstance(version, str) or not compatible_version(expected_version, version):
        raise RuntimeDiscoveryError(f"pcbnew {version!r} does not match kicad-cli {expected_version}")
    return version


def discover_python(cli, version, run, explicit=None):
    candidates = [explicit] if explicit is not None else list(python_candidates(cli))
    failures = []
    for candidate in candidates:
        try:
            probe_python([candidate], version, run)
            return [candidate]
        except (RuntimeError, OSError) as exc:
            # Import tracebacks are useful in a probe log, but a concise final
            # exception is enough to identify missing modules or an ABI mismatch.
            lines = str(exc).strip().splitlines()
            failures.append(f"{candidate}: {lines[-1] if lines else type(exc).__name__}")
    tried = "; ".join(failures) or "no candidate interpreters found"
    if explicit is not None:
        raise RuntimeDiscoveryError(
            f"Configured --kicad-python cannot load compatible pcbnew bindings ({tried}). "
            "Choose the Python interpreter supplied by your KiCad installation.")
    raise RuntimeDiscoveryError(
        f"No Python interpreter with pcbnew bindings matching kicad-cli {version} was found. "
        f"Tried: {tried}. uv's isolated tool Python normally cannot see system KiCad bindings. "
        "Use --kicad-python /path/to/kicad-python (typically /usr/bin/python3 on Linux), "
        "install the Python bindings from your KiCad distribution, or use --runtime flatpak.")
