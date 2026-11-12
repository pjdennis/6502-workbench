# Overview: the projects and how they came about

This is a single-document tour of the repository: what software and hardware it holds, how the projects relate, and the history of the work as the files and the git log show it. It is a companion to two shorter documents: the root [`README.md`](../README.md) (the map and quick start) and [`history.md`](history.md) (the milestone table, how to build an older era, and where files moved).

Written 2026-11-10 from the repository's documentation and its 3,477 commits (2020-07-20 to 2026-10-26). Where something is read off the commit log rather than stated in a document, the text says so.

## In one paragraph

The repository is one person's six-year exploration of the 6502, starting from a Ben Eater-style breadboard computer in July 2020. It grew in two directions. On the hardware side there are three homebrew single-board computers (**Wendy**, **Michael** and **Wendy 2**) and the firmware, drivers and add-on boards written for them, most recently an FPGA bus and an Ethernet web server on Michael. On the software side there is a tower of self-built tools: a 6502 assembler bootstrapped from a 129-byte seed, a vi-like editor written in that assembler's dialect, a Prog8 compiler that compiles itself on the target, and an emulator that models the boards chip by chip so that all of it can be tested without the hardware.

## How the pieces fit

```
                    host PC                                  6502 side
  ┌──────────────────────────────────────┐     ┌──────────────────────────────────┐
  │ vasm ─► firmware/ (libraries,        │     │ Wendy (2020)   Michael (2021)    │
  │         board configs, programs) ────┼──►  │ Wendy 2 (2022)                   │
  │ tools/upload (bit-banged serial)     │     │   + keyboard board, SPI display, │
  │                                      │     │     FPGA bus, W5500 Ethernet     │
  │ emulator/  nmos-default ◄── asm/ 00…17, editor/, prog8/ p1 run here          │
  │            wendy2c, michael ◄── the same firmware binaries run here          │
  └──────────────────────────────────────┘     └──────────────────────────────────┘
```

- **Firmware** is assembled on the host with vasm and sent to a board over a serial link the firmware bit-bangs through the 6522 VIA, or burned into an EEPROM.
- **The emulator** has two roles. Its `nmos-default` machine is a plain 6502 with host calls (files, console, arguments), which is where the assembler chain, the editor and the Prog8 compilers run. Its `wendy2c` and `michael` machines model the real boards, so the same firmware binaries run unchanged on the emulator and on the hardware.
- **The assembler, editor and Prog8 compiler** are 6502 programs. They depend on vasm for nothing: the assembler builds itself from a small C seed, and it builds the editor.

## The hardware

All three boards pair a 6502-family CPU with a 6522 VIA. None has a serial chip (ACIA): serial receive is bit-banged through the VIA's shift register and timers, and the host's DTR line resets the board. Details: [`hardware/README.md`](../hardware/README.md).

| Board | Year | CPU and clock | Character |
|---|---|---|---|
| **Wendy** (v1) | 2020 | 5 MHz | The first breadboard, after Ben Eater's design. HD44780 LCD in 4-bit mode (16x2, later 20x4), banked RAM and an SD chip select on port A. |
| **Michael** (v2) | 2021 | 65C02, 2 MHz | Built up from a bare CPU with an Arduino Mega standing in for the missing parts. It ends up matching the Ben Eater board, then gains the most peripherals of the three. |
| **Wendy 2** | 2022 | 65C02, 4 MHz then 9.72 MHz | A new design with GAL22V10 glue logic, a 512K RAM chip banked in two regions, and a dual-speed clock. Three revisions in three weeks; revision c is the current one. |

### Michael's peripherals

Michael is where most of the hardware experiments happened ([`hardware/michael/README.md`](../hardware/michael/README.md)):

- **Arduino bring-up (2021-01).** The Arduino generates the clock and answers the bus as ROM, RAM and an output port. Real RAM, then the real EEPROM (programmed in circuit by the Arduino), replace the emulated ones.
- **PS/2 keyboard board** with external shift registers (2021-04). A two-way version has its own schematic. Its way of finding the end of a byte loses some keyboards' replies; [`michael-keyboard-frame-detection.md`](michael-keyboard-frame-detection.md) has the scope measurements.
- **SPI graphic display** (ILI9341), first through a board of 74-series logic designed in Logisim and Digital (2022-09).
- **FPGA attempts** on a Digilent Cmod A7: the 74-series circuit transcribed (2024-10), then hand-written Verilog at 128 MHz, flaky and set aside (2025-04).
- **A two-way SPI interface** in 74LS chips, then in a GAL20RA10 and a 74HC299 (2025-10).
- **The FPGA bus** (2026-10): the Cmod A7 becomes a general bus on three pins shared with the LCD. Its devices are the display (raw commands and a text mode with hardware scrolling) and the network.
- **W5500 Ethernet** (2026-10): first on the GAL SPI interface, where it answered ping, then on the FPGA bus, where Michael serves a web page.

### Wendy 2's memory design

Revision c's PLD ([`hardware/wendy2/22V10-wendy2c.pld`](../hardware/wendy2/22V10-wendy2c.pld)) decodes 15 lower banks at `$0000–$3FFF` (used for multitasking), fixed RAM at `$4000–$7FFF` and 8 upper 32K banks, and runs ROM accesses at half clock speed. The emulator generates its decode logic directly from this file.

## The software projects

### Firmware (`firmware/`)

6502 assembly for the real boards, assembled with vasm. See [`firmware/README.md`](../firmware/README.md).

- **Shared libraries** (`lib/`): HD44780 LCD routines for 4-bit and 8-bit wiring, delays and number conversion, text and full-screen consoles with a command table and REPL, a PS/2 keyboard driver with key translation and typematic, sound (tones, musical notes, Morse), graphics (ILI9341 driver, fonts, a graphics console), the FPGA bus and W5500 drivers, and the serial loaders.
- **Board support** (`boards/`): each board's configuration, machine initialization and RAM/EEPROM loaders. Michael also has a ROM with a loader and LCD/keyboard services; Wendy 2 has a boot monitor.
- **Programs** (`programs/`): over 100 programs, from the first LED and LCD tests to preemptive multitasking demos, songs, a Brainf\*\*\* compiler, a line editor, a merge sort across RAM banks, BBC BASIC running through a MOS shim, and the web server.
- **Regression check**: `firmware/manifest.txt` holds the hash of every program's binary. It was the safety net for the 2026 reorganization and the port from vasm 1.9f to 2.0.

### The assemblers (`asm/`, `attic/asm1/`)

Two generations of self-hosting 6502 assembler, both written in 6502 assembly.

- **asm1** (2022-11 to 2025-11, now in [`attic/asm1/`](../attic/asm1/)) was seeded by a version written in vasm syntax and reached byte-identical self-assembly on 2025-11-15. It brought the first emulator with it: a single C file on the fake6502 core.
- **asm2** (2026, now [`asm/`](../asm/)) removes the dependence on any outside assembler. Stage `00` is a C program that only understands `DATA $XX` bytes and produces a 129-byte assembler. Each of stages `01`–`16` is assembled by the stage before it and adds what the next needs: labels, two passes, hash tables, `.include`, sections, local labels, standard 6502 syntax, expressions, conditional assembly, macros. Stage `17` is the live assembler and must reassemble itself byte for byte. [`asm/BOOTSTRAP-OVERVIEW`](../asm/BOOTSTRAP-OVERVIEW) lists each stage's step.

The stage-17 test files are the executable specification of the dialect. There is also a Python work-alike (`pyasm.py`) and syntax highlighting for Vim and VS Code.

### The editor (`editor/`)

A vi-like text editor of about 10,700 lines of assembly, built by stage 17 ([`editor/README.md`](../editor/README.md)). It has normal, insert and command modes, counts, word motions and operators, yank and paste, search, marks, range commands and single-level undo/redo. Much of its history is about doing little work per keystroke: a render decision engine, partial repaints, terminal insert/delete-character and scroll sequences, and batching of typed-ahead keys. It runs in the emulator's console and terminal modes, and on Michael, on the 20x4 LCD and on the graphic display through the FPGA's text mode. Its sources are split so that it can edit itself.

### The Prog8 compilers (`prog8/`)

A bootstrap chain for [Prog8](https://github.com/irmen/prog8), a high-level language for 6502 machines, patterned on the assembler chain ([`prog8/README.md`](../prog8/README.md)).

- **`p8c`**: a host compiler in Python, the test oracle.
- **`tinyp8`**: the first on-target compiler, hand-written in assembly and then rewritten in Prog8; both versions produce identical output.
- **`p1`**: the on-target compiler written in Prog8. Too large for one 64K binary, it runs as two passes that exchange the syntax tree through a file. Running on the emulator, it compiles its own source to output byte-identical to `p8c`'s.
- **`upstream/`**: p1 ported to the official Prog8 compiler (prog8c 12.1.1), with custom targets for the emulator and for Wendy 2's banked memory. p1 also self-hosts on the emulated banked Wendy 2.

### The emulator (`emulator/`)

A C emulator with three machines ([`emulator/README.md`](../emulator/README.md)):

- **`nmos-default`**: the host-stub machine for the assembler, editor and compilers, with console and ANSI terminal modes.
- **`wendy2c`**: ROM, 512K banked RAM, the PLD, VIA, LCD, serial bridge, LED, button and piezo.
- **`michael`**: the board, its PS/2 keyboard board, the FPGA bus and graphic display, the GAL SPI interface and the W5500 with a network client, including models of the real board's faults (keyboard faults, chip select glitches).

Front ends include a live terminal view, a browser UI over WebSocket, audio output, and a serial link that the real upload tools can drive. The CPU core is checked against the Klaus Dormann and Tom Harte test suites.

### Tools and research

- [`tools/`](../tools/): serial upload (`transfer.py`, a daemon that holds the port open, the format 3 framing), the firmware manifest check, a webcam OCR reader for the Wendy 2 LCD (used to capture the real display's font for the emulator), Michael's ROM builder, and the build and test drivers.
- [`research/bbc-basic-iv/`](../research/bbc-basic-iv/): a byte-level analysis of how BBC BASIC IV's 16K ROM divides between floating point, the assembler, the evaluator and so on.
- [`attic/`](../attic/): superseded or unmerged work kept for review, including asm1 and a never-merged 6502 web server for the emulator's socket API.

## History

### Activity by year

Commit counts, from the git log:

| Year | Commits | Main work |
|---|---|---|
| 2020 | 186 | Wendy: display, multitasking, serial loader, mini display graphics |
| 2021 | 201 | Michael's bring-up and keyboard; LCD library rework; line editor |
| 2022 | 164 | Wendy 2 and its revisions; Michael's SPI display; asm1 begins |
| 2023 | 326 | Michael's graphics console and keyboard driver; asm1 continues |
| 2024 | 7 | BBC BASIC on Michael (FPGA display work happened outside the repository) |
| 2025 | 18 | asm1 self-hosts (logic-chip and GAL SPI designs outside the repository) |
| 2026 | 2,575 | asm2, editor, emulator, Prog8, reorganization, Michael's ROM, FPGA bus and network |

The work comes in bursts of a few weeks separated by quiet months. 2026 holds three quarters of all commits.

### 2020: Wendy, a breadboard and a loader

The first commit (2020-07-20) is a Ben Eater-style computer already running display code. Within a week the commits show hardened LCD routines, a ticks counter, a console, and relocatable processes run from RAM: the start of the multitasking demos. August (127 commits, the busiest month of the early years) is mostly the **serial upload-and-run loader**: assemble on the PC, send to RAM with a checksum, run. The log shows the struggle to receive serial data with only a VIA ("working ish", "Actually this one works"), the baud rates climbing, and the interrupt vector moved into RAM so that uploaded programs can take interrupts. September adds a small graphic display with fonts and Bresenham line drawing, and the `wai` instruction to sleep between interrupts.

### 2021: Michael, built from the CPU outward

January's Arduino sketches build Michael up in stages (see above). In April the board runs standalone, and the keyboard work begins: scan codes on a console, set 3 decoding, key translation, typematic rate. By 2021-04-09 uploads work on Michael and the configuration splits into `base_config_v1.inc` and `base_config_v2.inc`, so one library serves both boards. December (90 commits) reworks the display routines so they need no delays, moves Michael to an 8-bit LCD interface and a 20x4 display, and builds a line editor with insert and cursor movement on the keyboard.

### 2022: Wendy 2, a display for Michael, and the first assembler

April brings **Wendy 2** (2022-04-10), with banking added on 04-23 (rev b) and the 512K memory map and PLD on 04-30 (rev c). In June the crystal is swapped for 9.72 MHz and the rev b code is removed in July. September gives Michael its **SPI graphic display** with text, a larger character set and a flashing cursor. On 2022-11-19 **asm1** begins; within a week it has a hash table for labels and instructions.

### 2023–2025: a long branch and a slow bootstrap

In April 2023 a branch, `michael_keyboard_wip`, forks from `main` and carries Michael's work for three years: a graphics console with a command prompt, a reusable keyboard driver, smaller fonts, and a Brainf\*\*\* compiler run from the command line. The log for May and June 2023 also shows asm1 gaining automatic operand sizing, sections, arguments and include-file error reporting. On 2024-02-11 **BBC BASIC runs on Michael** through a MOS shim. The repository is then nearly silent for 21 months, though the documents written later record hardware work in that gap: the two FPGA display attempts and the logic-chip and GAL SPI interfaces. In November 2025 asm1 is optimized and, on 2025-11-15, assembles itself byte-identically.

### 2026, January–February: asm2 and the editor

asm2 enters version control on 2026-01-06 and gets its C seed two days later. January's commits add macros, scopes, expressions and out-of-memory checks. February is the busiest month in the repository (836 commits): the stages move into their own directories, the chain is renumbered from 00–23 to 00–17, the emulator is split out, and the **editor** goes from its first program (02-07) to word motions, search, marks, undo and a long series of render optimizations, each with tests.

### 2026, May–July: board-accurate emulation and Prog8

In May the assembler's source stack and macro frames are reworked, and the emulator gains the **`wendy2c` machine** (2026-05-12), the Tom Harte CPU tests, and the webcam LCD reader. From 2026-05-31 the **Prog8** work runs for a month: the host compiler's walking skeleton, `tinyp8`, then `p1`, which **self-hosts on 2026-06-07**, followed by the upstream port and the banked Wendy 2 targets. Early July reduces the editor's size by about 3 KB and adds more undo.

AI assistance is recorded in the history. Commit messages carry AI co-author lines from the first day of asm2 (2026-01-06), and from 2026-05-07 some commits are authored as "Claude" outright (471 of them). The repository has `CLAUDE.md` guidance files, and several unmerged `claude/…` branches are preserved as `archive/` tags.

### 2026, September: reorganization

Until now everything lived at the repository root or in `assembler/` and `assembler2/`. On 2026-09-24 the repository was **reorganized**: `michael_keyboard_wip` was merged at last, files moved into the present layout, stale material went to the attic, CI was added, and the work continued in a new repository, `pjdennis/6502-workbench`, with the full history and a tag for every old branch. A second move on 09-29 dissolved `toolchain/`. The same weeks ported the firmware to vasm 2.0 with every binary unchanged, gave Michael a new **ROM** and **upload format 3** (09-27), fixed dozens of editor edge cases against vim's behaviour, and brought the editor up on the real Michael.

### 2026, October: Michael gets an FPGA bus and a network

- 10-03: the FPGA replaces the 74-series display board as a drop-in.
- 10-04: it becomes the general **FPGA bus**, with the display driver moved onto it, then a text mode with hardware scrolling.
- 10-07: the editor runs on the graphic display.
- 10-25: the GAL SPI interface drives a **W5500** and Michael answers ping; the W5500 then moves to the FPGA bus and Michael runs a **web server**, reachable from phones on the home Wi-Fi.
- 10-26: the server handles four sockets and browsers' idle connections.

Each step was modelled in the emulator, including the board's chip select glitches, and tested there.

## Threads that run through the history

- **Bootstrapping and self-hosting.** asm1 from a vasm seed, asm2 from 129 bytes, Prog8 from a Python compiler to one that compiles itself. Each uses the same strict test: the tool must reproduce itself byte for byte.
- **Substituting for missing hardware.** The Arduino stood in for Michael's chips in 2021; the emulator stands in for whole boards from 2026, down to their faults.
- **One library, several boards.** Since 2021 the per-board `base_config` files let the same drivers and demos build for each board.
- **Regression by hash and by golden.** The firmware manifest, the byte-identical self-assembly checks, LCD golden frames and editor screen tests make large refactorings safe. Test-driven development is the stated convention from 2026.
- **History kept intact.** Nothing has been rewritten. Old commits still build as they did, moves are pure `git mv` commits, unmerged branches survive as tags, and superseded work sits in the attic rather than being deleted.
- **A personal project.** The boards have names, a song lost the part "that Angel did not like" in 2020, and the 2026 web page carries a note for Angel.

## Where to read more

| Topic | Document |
|---|---|
| Milestone commits, tags, building old eras, file moves | [`history.md`](history.md) |
| Boards and revisions | [`hardware/README.md`](../hardware/README.md), [`hardware/michael/README.md`](../hardware/michael/README.md), [`hardware/wendy2/README.md`](../hardware/wendy2/README.md) |
| Michael's SPI and FPGA designs | [`michael-spi-interface-logic-designs.md`](michael-spi-interface-logic-designs.md), [`michael-fpga-display-earlier-designs.md`](michael-fpga-display-earlier-designs.md), [`michael-fpga-bus-plan.md`](michael-fpga-bus-plan.md), [`michael-fpga-w5500-plan.md`](michael-fpga-w5500-plan.md) |
| Firmware layout and vasm rules | [`firmware/README.md`](../firmware/README.md) |
| Assembler chain | [`asm/README.md`](../asm/README.md), [`asm/BOOTSTRAP-OVERVIEW`](../asm/BOOTSTRAP-OVERVIEW) |
| Editor | [`editor/README.md`](../editor/README.md) |
| Prog8 | [`prog8/README.md`](../prog8/README.md), [`prog8/PLAN.md`](../prog8/PLAN.md) |
| Emulator | [`emulator/README.md`](../emulator/README.md) |
| The 2026 reorganization | [`REORGANIZATION_PLAN.md`](REORGANIZATION_PLAN.md) |
