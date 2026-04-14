# Example Release Configuration

`release.toml` here is a sample matching the Example PCB project.

Run from the repo root:

```bash
kicad-release --config example/release.toml
```

Output goes to `example/releases/3.2/` (directory created automatically).

For the schematic title block to populate correctly, the schematic must use
KiCad text variables (`${TITLE}`, `${REV}`, `${DATE}`, `${COMPANY}`) in the
title block fields. See the repo README for one-time setup.
