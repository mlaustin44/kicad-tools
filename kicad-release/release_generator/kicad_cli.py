"""Wrapper around `kicad-cli` subprocess invocations."""
from __future__ import annotations
import re
import shutil
import subprocess
from pathlib import Path

MIN_VERSION = (10, 0, 0)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class KicadCliError(RuntimeError):
    """Raised when kicad-cli fails or is missing/too old."""


def find_kicad_cli() -> str:
    path = shutil.which("kicad-cli")
    if not path:
        raise KicadCliError("kicad-cli not found on PATH")
    return path


def get_version() -> tuple[int, int, int]:
    try:
        out = subprocess.run([find_kicad_cli(), "version"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, timeout=10)
    except subprocess.TimeoutExpired as e:
        raise KicadCliError("kicad-cli version check timed out") from e
    except OSError as e:
        raise KicadCliError(f"failed to execute kicad-cli: {e}") from e
    if out.returncode != 0:
        raise KicadCliError(f"`kicad-cli version` failed: {out.stderr.strip()}")
    line = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
    m = _VERSION_RE.search(line)
    if not m:
        raise KicadCliError(f"unparseable kicad-cli version: '{line}'")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def check_version() -> None:
    v = get_version()
    if v < MIN_VERSION:
        raise KicadCliError(f"kicad-cli {'.'.join(map(str, v))} is too old; "
                            f"requires {'.'.join(map(str, MIN_VERSION))}+")


def run(args: list[str], *, cwd: Path | None = None, verbose: bool = False,
        timeout: int = 600) -> subprocess.CompletedProcess:
    """Invoke `kicad-cli` with the given args. Raises KicadCliError on failure.

    stdout is always captured and returned; `verbose` controls whether the command
    and stderr are echoed to the terminal.
    """
    cmd = [find_kicad_cli()] + args
    if verbose:
        print(f"$ {' '.join(cmd)}")
    try:
        res = subprocess.run(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise KicadCliError(
            f"kicad-cli {' '.join(args[:2])} timed out after {timeout}s"
        ) from e
    except OSError as e:
        raise KicadCliError(f"failed to execute kicad-cli: {e}") from e
    if verbose and res.stderr:
        print(res.stderr, end="")
    if res.returncode != 0:
        raise KicadCliError(
            f"kicad-cli {' '.join(args[:2])} failed (exit {res.returncode}): {res.stderr.strip()}"
        )
    return res
