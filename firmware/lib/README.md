# Firmware libraries

Shared routines, included by bare file name (see [`../README.md`](../README.md)). They are plain `.inc` files with no directory-level build: a program includes its board's `base_config_*.inc` first, defines the constants and zero-page locations a library asks for (each file's header comment says what it `Requires`), then includes the library.

| Directory | Contents |
|---|---|
| [`core/`](core/README.md) | 6522 registers, delays, buffers, number conversion, memory copy, macros |
| [`lcd/`](lcd/README.md) | HD44780 LCD routines (4-bit and 8-bit) and `lcd_screen.inc` |
| [`graphics/`](graphics/README.md) | SPI/parallel graphic display, fonts, graphics console |
| [`console/`](console/README.md) | Text consoles, command table, REPL |
| [`keyboard/`](keyboard/README.md) | PS/2 keyboard driver and key tables |
| [`sound/`](sound/README.md) | Tones, notes, morse |
| [`tasks/`](tasks/README.md) | `prg_*` tasks for the multitasking demos |
| [`serial/`](serial/README.md) | The bit-banged serial upload loaders |
| [`fpga/`](fpga/README.md) | The Michael FPGA bus driver (`fpga_bus.inc`) |
