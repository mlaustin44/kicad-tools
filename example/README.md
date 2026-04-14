# Example Release Configuration

`release.toml` here is a sample configuration. It references the generic
title block templates in `../templates/`, which have an empty logo cell.

Run from the repo root:

```bash
kicad-release --config example/release.toml
```

Output goes to `example/releases/3.2/` (directory created automatically).

For the schematic title block to populate correctly, the schematic must use
KiCad text variables (`${TITLE}`, `${REV}`, `${DATE}`, `${COMPANY}`) in the
title block fields. See the repo README for one-time setup.

## Local overrides

To point at your own customized templates (e.g. with an embedded logo)
without modifying the committed example, copy `release.toml` to
`release.local.toml` and edit the `[titleblock].template` and
`[assembly_drawing].template` paths. Files matching `*.local.toml` are
gitignored.

```bash
cp example/release.toml example/release.local.toml
# edit template paths, then:
kicad-release --config example/release.local.toml
```
