# Title Block Templates

`titleblock_a4.svg` is a minimal programmatically-generated A4-landscape starter.
It has every placeholder and region the kicad-release tool expects, with
invisible region rects (`fill="none" stroke="none"`) so unused regions don't
show up as empty boxes in the output PDF.

Intended workflow: open in Inkscape to refine the visual layout — adjust the
title-block borders, fonts, logo placement, revision-history cells — while
preserving the placeholder strings and region ids. The tool only cares about
the presence and bounding box of each `<rect id="...">`, not its appearance.

See the top-level README for the full list of placeholders, regions, and the
authoring contract.
