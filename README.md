# kicad-tools

Tools for KiCad PCB design workflows.

## kicad-release

A CLI tool that generates a complete versioned production release package from
a KiCad 10 project: schematic PDF, fab/assembly drawings, gerbers, drill,
pick-and-place, BOM.

### Install

```bash
git clone <repo> && cd kicad-tools
python -m venv .venv
.venv/bin/pip install -e .
```

Requires:
- Python 3.11+
- KiCad 10+ (`kicad-cli` on PATH)
- Optionally: Inkscape (used as a fallback if CairoSVG fails on a particular SVG)

### Usage

```bash
# Full release
kicad-release --config release.toml

# Single step
kicad-release --config release.toml --only fab-drawing

# Dry run (list steps without executing)
kicad-release --config release.toml --dry-run

# Keep intermediate scratch files (useful for debugging fab/assembly layout)
kicad-release --config release.toml --keep-scratch

# Verbose (stream kicad-cli output)
kicad-release --config release.toml --verbose
```

See `example/release.toml` for a full annotated config.

### One-time setup: schematic title block

For the schematic PDF's title block fields to be populated by the tool, the
schematic must reference KiCad text variables in the title block. In KiCad:

1. Open the schematic in eeschema.
2. File → Schematic Setup → Project → Text Variables.
3. Leave the table empty — the tool injects `TITLE`, `REV`, `DATE`, and
   `COMPANY` at export time via `kicad-cli --define-var`. Just reference
   `${TITLE}`, `${REV}`, `${DATE}`, `${COMPANY}` in the title block fields.

The `.kicad_sch` file is **never modified** by this tool — variables are
injected at export time only.

### Title block templates

Title blocks are SVG files authored in Inkscape. See `templates/README.md`
for the authoring contract (placeholders, `id="region"` rects, units).

### Spec and design

See `docs/superpowers/specs/2026-04-14-kicad-release-tool-design.md`.

### Tests

```bash
.venv/bin/pytest tests/ -v
```

Integration tests exercise `kicad-cli` against a real project. Set
`KICAD_TEST_PROJECT` to point at a KiCad 10 project directory; otherwise
they fall back to the default path in `tests/conftest.py` and skip cleanly
if it's not present.
