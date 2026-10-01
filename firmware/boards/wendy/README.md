# Wendy (v1)

5 MHz, VIA at `$6000`, 4-bit LCD on PORTB; PORTA carries RAM bank select and an SD chip select (see [`hardware/README.md`](../../../hardware/README.md)).

- `base_config_v1.inc`, `initialize_machine_v1.inc`: configuration and port setup.
- `upload_and_run_ram_v1.s`, `upload_and_run_eeprom_v1.s`: format 1 loaders (`firmware/lib/serial/upload_and_run.inc`).

Programs are in `firmware/programs/wendy/`; upload with `tools/upload/compile_and_upload_wendy.sh`.
