# Docs

| File | What it is |
|---|---|
| [`history.md`](history.md) | The repository's timeline, how to check out and build an older era, and where files moved in 2026-09. Start here. |
| [`REORGANIZATION_PLAN.md`](REORGANIZATION_PLAN.md) | The plan for the 2026-09-24 reorganization, with what was done. Done; uses the paths of its time. |
| [`michael-rom-plan.md`](michael-rom-plan.md) | The plan for Michael's new ROM (loader and LCD/keyboard services in EEPROM). Done (2026-09-27). |
| [`michael-keyboard-frame-detection.md`](michael-keyboard-frame-detection.md) | Why some keyboards' command replies are lost on Michael (the frame detector's idle time), the measurements, the recommended hardware change (count clock pulses) and TODOs. Open (2026-09-30). |
| [`michael-upload-format-3-plan.md`](michael-upload-format-3-plan.md) | The plan for upload format 3, which replaced format 2 on Michael. Done (2026-09-27). The implementation is `firmware/lib/serial/upload_v3.inc` and `tools/upload/upload_frame.py`. |

Documentation for the other areas lives beside their code: [`asm/`](../asm/), [`editor/`](../editor/), [`prog8/`](../prog8/), [`emulator/`](../emulator/), [`firmware/`](../firmware/), [`hardware/`](../hardware/) and [`tools/`](../tools/). Michael's schematics are in [`hardware/michael/schematics/`](../hardware/michael/schematics/). The root [`README.md`](../README.md) has the map.
