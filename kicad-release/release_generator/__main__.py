"""CLI entry point."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from . import __version__
from .pipeline import run_pipeline, STEP_NAMES


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kicad-release",
        description="Generate a production release package from a KiCad project. "
                    "Defaults to ./release.toml if --config is not given.",
    )
    p.add_argument("--config", help="Path to release.toml (default: ./release.toml)")
    p.add_argument("--only", action="append", default=None, metavar="STEP",
                   help=f"Run a single step (repeatable). Valid: {', '.join(STEP_NAMES)}")
    p.add_argument("--dry-run", action="store_true",
                   help="Print steps and outputs without executing")
    p.add_argument("--keep-scratch", action="store_true",
                   help="Keep intermediate files in releases/{ver}/.scratch/")
    p.add_argument("--verbose", action="store_true",
                   help="Stream full kicad-cli output")
    p.add_argument("--version", action="version", version=f"kicad-release {__version__}")
    return p


def _resolve_config(explicit: str | None) -> str | None:
    """If --config wasn't given, default to ./release.toml in the cwd."""
    if explicit:
        return explicit
    default = Path.cwd() / "release.toml"
    if default.exists():
        return str(default)
    print("error: no --config given and no release.toml in the current directory",
          file=sys.stderr)
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = _resolve_config(args.config)
    if config_path is None:
        return 1
    return run_pipeline(
        config_path=config_path,
        only=args.only,
        dry_run=args.dry_run,
        keep_scratch=args.keep_scratch,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
