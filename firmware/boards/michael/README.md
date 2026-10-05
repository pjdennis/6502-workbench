# Michael (v2)

2 MHz, VIA at `$6000`, 8-bit LCD, PS/2 keyboard through shift registers (see [`hardware/michael/`](../../../hardware/michael/README.md)).

Board files:
- `base_config_v2.inc`, `initialize_machine_v2.inc`, `michael_ports.inc` (the VIA port setup as a macro).
- `upload_and_run_ram_v2.s`, `upload_and_run_eeprom_v2.s`: the older format 1 loaders. `_eeprom_v2.s` doesn't match any board now.

The ROM (`hardware/michael/michael_rom.bin`):
- `michael_rom.s`: loader (`firmware/lib/serial/upload_v3.inc`, format 3), services and vectors.
- `michael_rom.inc`: hand-written entry points and RAM map, the source of truth for programs.
- `michael_services.inc`: the editor's environment on the LCD and keyboard; `michael_graphic_screen.inc`: its screen on the graphic display instead (the FPGA's text mode), chosen with `SVC_SCREEN_SELECT`. `michael_editor_layout.inc`: the RAM split between the ROM and the editor, read by both vasm and asm17.

Build with `firmware/vasm`; `tools/tests/test_michael_rom.py` checks the committed image is this build. Programs are in `firmware/programs/michael/`; upload with `tools/upload/compile_and_upload_michael.sh`.
