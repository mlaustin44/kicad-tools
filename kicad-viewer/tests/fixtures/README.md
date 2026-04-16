# Fixtures

Real KiCad 10 project used as the test fixture.

- `pic_programmer.*` — from KiCad's built-in demos (GPL-licensed, included with
  KiCad at `/usr/share/kicad/demos/pic_programmer/`). Comprises
  `pic_programmer.kicad_pro`, `pic_programmer.kicad_pcb`, and two schematics
  (`pic_programmer.kicad_sch` root + `pic_sockets.kicad_sch` child).
- `pic_programmer.glb` — generated via `kicad-cli pcb export glb --subst-models --force`.

To regenerate the .glb:

    kicad-cli pcb export glb pic_programmer.kicad_pcb -o pic_programmer.glb --subst-models --force

Two warnings about missing 3D models (`textool_40.wrl`, `adjustable_rx2v4.wrl`)
are expected; kicad-cli still produces a valid `.glb` without them.
