# Vendored KiCad parser

Files in this directory are copied from [KiCanvas](https://github.com/theacodes/kicanvas)
at commit `2890714705df9378fb09cc89c0776582da21cc96` (vendored 2026-04-13). MIT licensed.

## What was copied

From `kicanvas/src/kicad/`:

- `tokenizer.ts`, `parser.ts`, `common.ts` — s-expression tokenizer and parser
- `board.ts`, `schematic.ts` — typed models of parsed `.kicad_pcb` / `.kicad_sch`
- `project-settings.ts` — `.kicad_pro` parser
- `drawing-sheet.ts` — `.kicad_wks` / title-block parser
- `theme.ts` — theme-type interfaces (used by `drawing-sheet.ts` etc.)
- `default_drawing_sheet.kicad_wks` — bundled default title block
- `kicad_wks.d.ts` — module declaration for `*.kicad_wks` imports
- `text/` — stroke-font engine (`font.ts`, `stroke-font.ts`, `glyph.ts`,
  `eda-text.ts`, `lib-text.ts`, `sch-text.ts`, `sch-field.ts`, `markup.ts`,
  `newstroke-glyphs.ts`)
- `index.ts` — barrel re-exports

From `kicanvas/src/base/` (pulled in as `./base/` because the parser files
depend on them transitively):

- `color.ts` — `Color` class
- `types.ts` — `is_number`, `is_string`, `is_iterable`, `is_array`, etc.
- `log.ts` — `Logger` helper and `*` re-export
- `array.ts` — `as_array`
- `object.ts` — `merge`
- `math/` — `angle.ts`, `arc.ts`, `bbox.ts`, `camera2.ts`, `matrix3.ts`,
  `vec2.ts`, `index.ts`

## What was stripped or rewritten

All imports from `../base/`, `../../base/`, `../graphics/`, `../viewers/`,
`../kc-ui/`, and `../kicanvas/` were rewritten or removed.

- `board.ts` and `schematic.ts` used `import type { Project } from "../kicanvas/project"`
  for an optional `project?: Project` field and (in `schematic.ts`) for
  optional-chained reads of `root_schematic_page?.document`. Replaced with a
  local minimal `type Project = ...` placeholder — the adapter never sets
  this field, so the shape only has to type-check.
- `text/font.ts` imported `Color, Polyline, Renderer` from `../../graphics`
  for the `Font.draw()` and `Font.draw_line()` methods. Those two methods
  were **deleted** (and the imports removed). Text *layout* is preserved
  (`get_line_extents`, `break_lines`, `get_text_as_glyphs`,
  `get_markup_as_glyphs`, `get_line_positions`, `wordbreak_markup`);
  callers that want to render stroke glyphs can walk the returned
  `Glyph`/`StrokeGlyph` data themselves.
- `drawing-sheet.ts` uses `import default_sheet from "./default_drawing_sheet.kicad_wks"`;
  KiCanvas bundles this via esbuild's "text" content type. For Vite we
  changed the import to `"./default_drawing_sheet.kicad_wks?raw"` so Vite
  returns the file contents as a string. The adjacent `kicad_wks.d.ts`
  module declaration is preserved so TypeScript still recognises the
  extension.

## Compiler-option relaxation

The SvelteKit app has `strict: true`, `noUncheckedIndexedAccess: true`, and
`exactOptionalPropertyTypes: true`. The vendored code inflates parser
classes with `Object.assign(this, parse_expr(...))` in the constructor, so
class fields lack initializers by design. To keep the rest of strict mode
intact we set **`strictPropertyInitialization: false`** in the app's
`tsconfig.json`. `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`
are still enabled globally; a handful of narrow, commented fixes in
`common.ts`, `board.ts`, and `schematic.ts` handle the remaining
strict-mode cases (see the `// exactOptionalPropertyTypes` and
`// Non-null assertion` comments).

## How we use it

`src/lib/adapter/adapter.ts` (added in task 11) imports from this module and
converts the parser's output into our own `Project` type (see
`src/lib/model/project.ts`). The rest of the app does not import from here
directly.

## Updating

To re-vendor:

1. Update the SHA in the reference clone (`references/kicanvas`).
2. Re-copy the files listed above.
3. Re-apply the strip/rewrite list (rewrite `../base/` → `./base/`,
   `../../base/` → `../base/`; replace the `kicanvas/project` imports;
   strip `text/font.ts`'s `draw` methods; change the `.kicad_wks` import to
   `?raw`).
4. Run `npm run check` until clean.
5. Record the new SHA here.
