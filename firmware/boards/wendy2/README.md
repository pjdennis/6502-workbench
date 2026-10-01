# Wendy 2 (rev c)

9.72 MHz 65C02, VIA at `$F000`, 4-bit LCD, 512K banked RAM behind a 22V10 PLD (see [`hardware/wendy2/`](../../../hardware/wendy2/README.md)).

- `base_config_wendy2c.inc`, `initialize_machine_wendy2c.inc`: configuration and port setup.
- `upload_and_run_ram_wendy2c.s`, `upload_and_run_eeprom_wendy2c.s`: format 1 loaders at 115200 baud.
- `wendy2c_monitor.s`: an alternate boot ROM that loads and runs programs listed in `autoexec` from the emulator's simulated SPI disk (`--disk`); see `prog8/WENDY2_DISK_BOOT_DESIGN.md`.

Programs are in `firmware/programs/wendy2/`; upload with `tools/upload/compile_and_upload_wendy2.sh`, or run in the emulator (`emulator/demo_wendy2c.sh`).
