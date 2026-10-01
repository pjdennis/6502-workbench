# Boards

Per-board configuration, machine initialisation and loaders. Each board has a directory; the file-name suffix (`_v1`, `_v2`, `_wendy2c`) names the board, so a program's `.include base_config_*.inc` line says which board it targets.

| Directory | Board | Contents |
|---|---|---|
| [`wendy/`](wendy/README.md) | Wendy (v1) | `base_config_v1.inc`, `initialize_machine_v1.inc`, RAM/EEPROM loaders |
| [`michael/`](michael/README.md) | Michael (v2) | the same, plus the ROM and its service includes |
| [`wendy2/`](wendy2/README.md) | Wendy 2 rev c | the same, plus `wendy2c_monitor.s` |

Every board has:
- `base_config_*.inc`: clock (`CLOCK_FREQ_KHZ`), VIA address, port pin assignments, `DISPLAY_BITS`.
- `initialize_machine_*.inc`: sets the VIA ports and LCD up.
- `upload_and_run_ram_*.s`: the loader for the board's serial upload to RAM (assembled as the boot ROM). `upload_and_run_eeprom_*.s`: the same for programs in EEPROM.
