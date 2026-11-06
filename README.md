# kicad-tools

Independent tools for KiCad workflows:

| Tool | Purpose | Interface |
| --- | --- | --- |
| [kicad-release](kicad-release/README.md) | Versioned production release packages, drawings, fabrication outputs and BOM | Python CLI |
| [kicad-viewer](kicad-viewer/README.md) | Read-only schematic, PCB and 3D project viewing | Svelte browser app |
| [kicad-stitch](kicad-stitch/README.md) | Ground-via perimeter, signal returns/fences, island repair and adaptive fill, verified with KiCad refill/DRC | Python CLI and reusable planning engine |

Each tool has its own package, dependencies and tests. See the individual README
for installation and usage.
