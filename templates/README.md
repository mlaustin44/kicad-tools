# Title Block Templates

Three SVG files that define the layout, labels, placeholders, and region
rectangles used by the kicad-release tool to compose fab and assembly
drawing PDFs.

## Files

- `titleblock_base_a4.svg` — master reference. Not consumed by the tool
  directly; maintained as a canonical source so that changes to the title
  block layout can be propagated to the two derived templates.
- `titleblock_fab_a4.svg` — identical to base, plus invisible region
  rectangles for `board-view`, `render-3d`, `drill-table`, `stackup-table`,
  and `fab-notes`. Used by the fab drawing step.
- `titleblock_assembly_a4.svg` — identical to base, plus invisible region
  rectangles for `front-view`, `back-view`, and `assembly-notes`. Used by
  the assembly drawing step.

## Customizing for your project

The shipped templates have an empty logo cell (x=220 to x=287, y=170 to
y=183 in the SVG coordinate system). To add your own logo:

1. Open the SVG in Inkscape.
2. Import your logo (`File → Import`). Embed rather than link.
3. Scale and position it inside the logo cell.
4. Repeat for each of the three templates, or edit the base and
   propagate to the other two.

## Per-project customization without editing the defaults

The cleanest pattern is to keep your customized templates in a project-
specific subdirectory (e.g., `templates/acme/`) and point your
`release.toml` at those files via the `[titleblock].template` and
`[assembly_drawing].template` settings. That way the committed defaults
remain unchanged.

## Contract

The tool looks for two things in each template:

- **Text placeholders** — `{{NAME}}` strings inside `<text>` or `<tspan>`
  elements. The tool replaces them with config values at render time.
- **Region rectangles** — `<rect>` elements with recognized `id`
  attributes. The tool reads the rect's `x`/`y`/`width`/`height`, removes
  the rect, and renders the corresponding content (board outline, 3D
  render, stackup table, etc.) scaled to fit that box.

See `docs/superpowers/specs/2026-04-14-kicad-release-tool-design.md` for
the full list of recognized placeholders and region IDs.
