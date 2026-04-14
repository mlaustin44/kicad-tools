"""Wrapper around `kicad-cli` subprocess invocations."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

MIN_VERSION = (10, 0, 0)


class KicadCliError(RuntimeError):
    """Raised when kicad-cli fails or is missing/too old."""


def find_kicad_cli() -> str:
    path = shutil.which("kicad-cli")
    if not path:
        raise KicadCliError("kicad-cli not found on PATH")
    return path


def get_version() -> tuple[int, int, int]:
    out = subprocess.run([find_kicad_cli(), "version"],
                         capture_output=True, text=True, timeout=10)
    if out.returncode != 0:
        raise KicadCliError(f"`kicad-cli version` failed: {out.stderr.strip()}")
    line = out.stdout.strip().splitlines()[0].strip()
    parts = line.split(".")
    if len(parts) < 3:
        raise KicadCliError(f"unparseable kicad-cli version: '{line}'")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2].split("-")[0]))
    except ValueError:
        raise KicadCliError(f"unparseable kicad-cli version: '{line}'")


def check_version() -> None:
    v = get_version()
    if v < MIN_VERSION:
        raise KicadCliError(f"kicad-cli {'.'.join(map(str, v))} is too old; "
                            f"requires {'.'.join(map(str, MIN_VERSION))}+")


def run(args: list[str], *, cwd: Path | None = None, verbose: bool = False,
        timeout: int = 600) -> subprocess.CompletedProcess:
    """Invoke `kicad-cli` with the given args. Raises KicadCliError on failure."""
    cmd = [find_kicad_cli()] + args
    if verbose:
        print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=cwd, capture_output=not verbose, text=True,
                         timeout=timeout)
    if res.returncode != 0:
        stderr = res.stderr if not verbose else "(streamed above)"
        raise KicadCliError(
            f"kicad-cli {' '.join(args[:2])} failed (exit {res.returncode}): {stderr}"
        )
    return res
