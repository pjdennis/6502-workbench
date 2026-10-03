# Hardware

Three single-board computers, all built around a 6502-family CPU with a 6522 VIA. None of them has an ACIA: serial is bit-banged through the VIA (shift register, timer 2 and CB2). DTR from the host is used as reset. Board configuration for the firmware lives in [`firmware/boards/`](../firmware/boards/).

| Board | First commit | Clock | VIA | Display | Notes |
|---|---|---|---|---|---|
| **Wendy** (v1) | 2020-07-20 (`d297d44`) | 5 MHz | `$6000` | HD44780, 4-bit on PORTB (16x2; 20x4 from 2021-12) | Ben Eater-style breadboard. PORTA carries RAM bank select and an SD chip select. The IRQ vector lives in RAM at `$3FFE`. Firmware: `base_config_v1.inc`. |
| **Michael** (v2) | 2021-04-09 (`eb3853c`, "RAM upload to Michael working") | 2 MHz | `$6000` | HD44780, 8-bit on PORTB with control lines on PORTA | Keyboard via external shift registers. SPI graphic display from 2022-09 (`hello_michael_spi.s`), through an FPGA interface from 2026-10 ([`michael/fpga/`](michael/fpga/spi-display/)). BBC BASIC via a MOS shim from 2024-02 (`ecfa0b0`). Firmware: `base_config_v2.inc`. [`michael/`](michael/) describes its Arduino-driven bring-up (the Arduino emulates ROM, RAM, I/O and clock, then loads real RAM and programs the EEPROM in circuit) and has the sketches and a 2023 ROM image. |
| **Wendy 2** | 2022-04-10 (`6be57cd`) | 4 MHz, then 9.72 MHz (2022-06-02, `ba13b19`) | `$F000` | HD44780, 4-bit on PORTA, E on PORTB | 65C02 with GAL22V10 glue logic. Three revisions; see [`wendy2/`](wendy2/). The emulator models rev c (`emulator/`, `--machine wendy2c`). Firmware: `base_config_wendy2c.inc`. |
