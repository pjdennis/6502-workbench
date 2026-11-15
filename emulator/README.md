# `emulator/`

A four-machine 6502 emulator:

- **`nmos-default`** — the original direct-memory NMOS 6502 used by the
  assembler bootstrap and the editor. Memory-mapped I/O at
  `$F006`/`$F009`/`$F00C` (read/write/error byte ports) and the rest of
  the file/console/socket ports the assembler relies on.
- **`wendy2c`** — a board-level model of the wendy2c machine: 28C256
  ROM, 512 KiB banked RAM, 22V10 PLD clock + chip-select decoder, 6522
  VIA, HD44780 LCD, serial-USB bridge, LED + button, all wired to a
  W65C02S core. Selected with `--machine wendy2c`.
- **`michael`** — a board-level model of Michael (v2), the Ben Eater-style
  board: 16 KiB RAM at `$0000` (`--ram` picks another decoding), 6522 VIA
  at `$6000`, ROM at `$8000`, a 20x4 HD44780 in 8-bit mode, and the PS/2
  keyboard board (`chips/ps2_keyboard_board.c`). With `--load`, the code
  file is loaded into RAM there, and without `--rom` the ROM holds only
  the vectors (reset to the load address, IRQ to `$3F00`) and the LCD
  starts as the ROM leaves it (two lines, display on, no cursor, clear),
  as programs run from the ROM's loader expect; without `--load`, the
  code file is the ROM image. Selected with
  `--machine michael`. With `--exit-report`, at exit it prints the LCD,
  the PA1 LED (lit while the pin is high) and a bus check: LCD
  strobes whose lines weren't driven, and spells of two devices driving
  PORTB at once. `--live` runs it in the terminal and `--web` in the
  browser (see [`--web` mode](#--web-mode)).
- **`bbcbplus`** — an Acorn BBC Model B+128 as far as a batch tool needs
  it: an NMOS 6502, the B+ memory map with sideways RAM and ROM slots, a
  banked ROM module in one slot (the Computer Concepts 128K carrier's
  switching, or a sixteen-bank scheme of this project's), and a MOS the
  emulator implements behind the documented entry points, with the
  filing system on a host directory. Selected with `--machine bbcbplus`;
  see [bbcbplus](#bbcbplus-the-bbc-model-b128).

The default machine is `nmos-default`; nothing about the assembler
bootstrap chain changed when the wendy2c work landed.

## Building and testing

Run these from the repository root (the tests open `emulator/...` paths
relative to the current directory):

```bash
make                     # build emulator/emulator.out
make test                # C unit tests + every end-to-end target below
make michael-goldens     # just the michael end-to-end tests
make wendy2c-goldens     # just the wendy2c end-to-end tests
make bbcbplus-goldens    # just the bbcbplus end-to-end tests (no vasm needed)
make sanitizers          # most C tests again under ASan/UBSan/LSan
make harte               # Tom-Harte ProcessorTests (opt-in; needs data)
```

`make test` runs the end-to-end targets first (they are its prerequisites),
then the C unit tests (written with the greatest framework). The end-to-end
targets are (`bbcbplus-goldens`, `compile-and-run`, `michael-goldens`, `michael-web`, `michael-display-web`, `wendy2c-goldens`,
`wendy2c-lcd-trace`, `wendy2c-merge-sort`, `wendy2c-serial-link`,
`wendy2c-live-sigint`, `wendy2c-web`, `wendy2c-lcd5x10`, `web-machine-switch`,
`web-audio-buffer`, `timer2-cycles`).
All but `bbcbplus-goldens`, `timer2-cycles` and `web-audio-buffer` skip with a warning if
`vasm6502_oldstyle` isn't on `PATH`, and the web tests also if Playwright
is missing (`web-audio-buffer` needs only Playwright); `timer2-cycles`
needs vasm.
The nmos-default tests (`terminal_tests.py`, `emulator_tests.py`) need the
assembler chain and run from `tools/check_all.sh emulator`. See
`tests/README.md` for each suite and the slow opt-in ones.

## CLI

```
emulator <code file> [options] [<arguments>]
emulator --server
```

Common options (run `emulator.out` with no arguments for the full list):

| Option | Notes |
|---|---|
| `--machine <name>` | `nmos-default` (default), `wendy2c`, `michael` or `bbcbplus` |
| `--cpu <variant>` | `nmos` or `65c02` (wendy2c and michael force `65c02`, bbcbplus `nmos`) |
| `--rom <path>` | wendy2c: ROM image; falls back to the positional code file. michael: ROM image; with `--load` the code file goes into RAM, without it the code file is the ROM |
| `--kbd-scancodes <list>` | michael: comma-separated hex bytes the keyboard sends once the program has set it up |
| `--keys <path>` | michael: keys to type once the program has set up the keyboard -- text, control codes and ANSI key sequences (see `ps2_keys.h`) |
| `--key-interval MS` | michael: milliseconds between typed keys (default 20) |
| `--fpga-log <path>` | michael: a line per FPGA bus transfer (a rising edge of E on PA2): `C hh` (command), `D hh` (data), `R` (reply read), `S` (status read) |
| `--add <name>[,<name>...]` | michael: hardware plugged in beyond the board's own (repeatable): `gal-spi`, the GAL20RA10 SPI interface and its 74HC299 on port B and PA2, in place of the FPGA board, which it unplugs (`chips/gal_spi.h`, `hardware/michael/spi-interface/`); `w5500`, the W5500 Ethernet controller, on the FPGA's network device (`$81`) or, with `gal-spi`, on its SPI with the chip select on PA0 (`chips/w5500.h`; its link reads up, at 100 Mbps full duplex); `w5500-cs-rc`, a 10 nF capacitor on that chip select, which the W5500 then sees change 20 µs late and which swallows shorter glitches (needs `w5500` and `gal-spi`); `w5500-cs-bounce`, the board's ground bounce: when more than two port B lines fall in one cycle, that chip select glitches and the W5500 starts its frame again (needs `w5500` and `gal-spi`); `w5500-cs-flaky`, the board after its ground fix: every 37th cycle in which port B lines fall, while the W5500 is selected, glitches it (needs `w5500` and `gal-spi`). The exit report's bus check counts the '299 among port B's drivers, and the report shows the W5500's network settings (IP, mask, gateway, MAC) |
| `--net-request <path>` | michael, with `--add w5500`: a client on the network (`chips/net_client.h`) connects to the W5500 once a socket listens on `--net-port` (default 80), sends the file's bytes 1 ms later and keeps what the server sends until the server closes the connection; then it connects again, `--net-connections` times in all (default 1). `--net-response <path>` keeps what the server sent; `--net-idle <n>` has the client first open n connections that send nothing and stay open until the server closes them, as a browser's early connections (or a phone gone to sleep) can; the exit report counts the connections and the bytes |
| `--kbd-fault <name>` | michael: `noedge`, `noirq`, `noack` or `resend` (see `tools/tests/test_michael_keyboard.py`) |
| `--ram <decode>` | michael: how RAM below the VIA is decoded: `16k` (the default: `$0000-$3FFF`), `eater` (Ben Eater's: reads of `$4000-$7FFF` find nothing, but writes there, the VIA's too, land in `$0000-$3FFF`), `full` (24K at `$0000-$5FFF`) or `mirror8k` (8K at `$0000-$1FFF`, repeated up to `$5FFF`); `firmware/programs/michael/michael_ram_map.s` shows which |
| `--serial-input <path>` | wendy2c, michael: bytes pre-queued into the SERIAL_USB chip |
| `--live` | wendy2c: live ANSI render of LCD, LED, button, VIA pins. michael: the LCD, with the terminal's keys typed on the PS/2 keyboard (Ctrl-] quits), paced to 2 MHz or `--mhz` |
| `--cycle-cap N` | max cycles before forced exit (decimal; default 200000000; no cap under `--live` unless this is given explicitly). For wendy2c this is oscillator ticks (~2 per CPU cycle); for `nmos-default` and `--server` it is CPU cycles. |
| `--load <hex>` | load address for the positional code file |
| `--input` / `--output` / `--error-output` | ports `$F006` / `$F009` / `$F00C` |
| `--dump` / `--no-dump` | memory dump on exit |
| `--console` / `--terminal` | full-screen UI modes (mutually exclusive) |
| `--mhz` / `--cpu-mhz` / `--baud` | wall-clock pacing + serial timing. `--mhz` is the CPU clock for nmos-default and michael (michael `--live` and `--web` default to 2; other michael runs are not paced), but the OSC crystal for wendy2c (CPU = OSC / 2) |
| `--pace-mask` / `--pace-log` / `--pace-polls` | test hook: after reading an input byte whose mask byte is not `0`, `con_ready` reports not-ready for N polls (default 2000), so the next key arrives only after the program went idle (a `wait_ready` in the pause times out, and the program's next request for input ends the pause); the log gets `<input read> <output written>` as each pause ends. In terminal mode the serial input is held before the first byte and after each such byte until the program asks for input with nothing pending and all its output sent, like a user who waits for the screen before typing (the log is not written there) |
| `--rows N` / `--cols N` | terminal-size overrides |
| `--direct-io` | the program calls the `scr_*` screen vectors and `con_read` returns key codes; the emulator converts to and from ANSI (`direct_io.c`) |
| `--wendy2-prog <path>` | wendy2c: preload a raw program into RAM at `--load` (default `$4000`) and start it there, skipping the serial boot |
| `--disk <dir>` | wendy2c: host directory behind the `$F800-$F80F` file-I/O port block (`chips/syscall_ports.h`). bbcbplus: the directory the MOS's filing system works in |
| `--bbc-*` | bbcbplus: see [bbcbplus](#bbcbplus-the-bbc-model-b128) |
| `--serial-link <path>` | wendy2c: Unix socket on which a client drives the serial RX line bit by bit (`wendy2c_emu_link.py`) |
| `--web` / `--web-port N` / `--web-bind ADDR` / `--web-root PATH` | wendy2c, michael: browser UI over HTTP + WebSocket (see [`--web` mode](#--web-mode) and `web/README.md`) |
| `--audio` / `--wav <path>` | wendy2c: play the PB7 piezo line live, or record it to a WAV |
| `--exit-report` | wendy2c, michael: at exit, print to stderr how the run ended, the final LCD frame (text and hex) and, on michael, the FPGA bus, the LED, the bus checks and the stack's lowest point. Off by default, so `--live` and `--web` runs end quietly; the tests and the headless scripts (`demo_wendy2c.sh`, `compile_and_run.sh --cycle-cap`, prog8's `wendy2_*run.sh`) pass it |
| `--lcd-trace <path>` | wendy2c, michael: append an LCD frame to the file each time the LCD changes |
| `--lcd-panel <type>` | wendy2c: `16x2` (default) or `16x1-5x10` render layout |
| `--show-repaints` | debug: flash repainted cells in `--console` / `--terminal` |
| `--strict-api` | test hook: each `$F006` call keeps only what its contract (`asm/17/environment.asm`) says. The flags it does not return come back inverted, and the screen calls change A and Y, so a program that relies on more fails its tests here rather than on a board. The server takes it as `API strict` / `API standard` |

## bbcbplus: the BBC Model B+128

`--machine bbcbplus` is an Acorn BBC Model B+128 as far as a batch tool
needs it: an NMOS 6502 at 2 MHz, the B+ memory map with its sideways
slots, a banked ROM module in one slot, and a MOS that the emulator
implements behind the documented entry points. No Acorn ROM is in the
repository or needed. It is batch only (`--live` and `--web` are refused)
and has no screen, keyboard or interrupts. `NOTES-bbcbplus.md` lists every
fact about the real machine and MOS this relies on, and which were checked
against a source.

```sh
# a program: loaded at --load and entered there; its RTS ends the run (status 0)
emulator/emulator.out prog.bin --machine bbcbplus --load 1900 --disk disk

# a * command, passed to OSCLI after reset ("*" and leading spaces optional)
emulator/emulator.out --machine bbcbplus --disk disk --bbc-command "RUN TOOL args"
emulator/emulator.out --machine bbcbplus --bbc-module tool.rom --bbc-command "TOOL args"

# the developer's form: the module holds RAM, filled from disk by a loader
emulator/emulator.out --machine bbcbplus --bbc-module-ram --disk disk --bbc-command LOADER
```

With `--bbc-command` no code file is needed (the first argument may be an
option). The run ends with exit status 0 when the command or program
returns, 1 when an error reaches the default BRKV handler (its message goes
to standard error), on a fault (below) or a failed `--bbc-strict` check,
and 2 at `--cycle-cap` (CPU cycles here). `--exit-report` prints the
cycles, the PC and how the run ended, ROMSEL and `$F4`, the module's slot,
scheme, form, bank and bank switches, the file traffic (files opened, and
bytes read and written by OSBGET, OSBPUT and OSGBPB: the MOS here charges
nothing for them, so these say what a real filing system would be asked to
do), and the checks with the first few offenders.

| Option | Notes |
|---|---|
| `--bbc-command TEXT` | passed to OSCLI after reset, from `$0700` (as a language's input line would be). Repeatable, up to 9: each further line is passed in turn, from `$0700` with the stack reset, when the one before returns (an error ends the run there) |
| `<code file> --load HEX` | without `--bbc-command`: the file put in main RAM at HEX and entered there (with both, the file is loaded and the command run) |
| `--disk DIR` | the host directory the MOS's filing system works in |
| `--bbc-sideways-ram LIST` | the slots that are sideways RAM (default `0,1,12,13`, the B+128's; `none`) |
| `--bbc-rom N=FILE` | a plain 16 KB ROM image in slot N (repeatable); in a sideways RAM slot it is loaded into the RAM |
| `--bbc-module FILE` | the module's image, bank 0 first: up to 131072 bytes (`cc128`) or 262144 (`direct16`) |
| `--bbc-module-slot N` | the module's slot (default 4; it may not be a sideways RAM slot or one given `--bbc-rom`) |
| `--bbc-module-bank N` | the module's bank at power on (default 0; the real latch powers up undefined): 0-7, or 0-15 for `direct16` |
| `--bbc-module-scheme S` | `cc128` (default) or `direct16`, below |
| `--bbc-module-ram` | the developer's form: the module holds RAM |
| `--bbc-shadow` | OSBYTE 132 (HIMEM) answers `$8000` instead of `$7C00` (mode 7); the shadow screen RAM itself is not modelled |
| `--bbc-page HEX` | OSBYTE 131 (OSHWM, PAGE) answers HEX instead of `$1900` |
| `--bbc-strict` | a write to MOS memory or a ROMSEL unlike `$F4` at a MOS call ends the run (status 1) |

### What is modelled

- **CPU**: the emulator's NMOS core (`cpu_core.c`, as `--cpu nmos`), with
  its cycle counts. The core runs an instruction at a time and makes the
  reads and writes the instruction needs, but none of the NMOS 6502's
  dummy accesses (an indexed read's read of the unfixed address, the
  byte after a one-byte opcode, a read-modify-write's second write). The
  1 MHz bus stretching for slow I/O is not modelled, nor is the 6512A's
  two-phase clock.
- **Memory**: `$0000-$7FFF` main RAM; `$8000-$BFFF` the sideways window,
  selected by ROMSEL (write only, at `$FE30` and its mirror `$FE38`;
  bits 0-3 the slot); with ROMSEL bit 7 set, `$8000-$AFFF` is the B+'s
  12 KB private RAM and `$B000-$BFFF` still the selected slot;
  `$C000-$FFFF` the MOS ROM, with `$FC00-$FEFF` I/O. Sideways RAM is
  written through the window while its slot is selected. An empty slot,
  and unmodelled I/O, read as the open bus: the last byte the data bus
  carried. ROM slots and the MOS ignore writes. Shadow screen RAM and
  `$FE34` (its select) are not modelled; neither are the VIAs, the video,
  the sound, the keyboard, the ADC, Econet, the Tube or any disc
  hardware.
- **The module** (`chips/bbc_module.c`): eight (`cc128`) or sixteen
  (`direct16`) 16 KB banks behind one socket. A ROM socket has no write
  line, so the module switches on reads of addresses at the top of its
  window. It sees only accesses made while its slot is selected and the
  private RAM does not cover the address, which leaves `$B000-$BFFF`,
  where the switching addresses are, even with ROMSEL bit 7 set.
  - `cc128` is the Computer Concepts 128K ROM carrier (SpellMaster's,
    1987), as MAME models it (`src/devices/bus/bbc/rom/pal.cpp`,
    `bbc_ccispell_device`): with `offset = address - $8000`, a read of
    `$3FE0` selects bank 0 from any bank; only while the bank is 0, a
    read in `$3FC0-$3FDF` selects bank 1, `$3FA0-$3FBF` bank 2, ...,
    `$3F00-$3F1F` bank 7. The byte returned is the newly selected bank's.
  - `direct16` is this project's own design in the same manner: a read
    of `$BFF0+n` selects bank n, from any bank; no other address switches.
  - Writes never switch. In the ROM form they are ignored. In the RAM form
    (`--bbc-module-ram`), the developer's form, as someone would use to
    iterate without burning a ROM, a write to `$8000-$BFFF` while the slot
    is selected writes the selected bank. It starts empty unless
    `--bbc-module` preloads it; a loader fills it bank by bank (select the
    bank, then write the window, for example with OSGBPB) and enters its
    type in the ROM type table (`$02A1+slot`) as sideways RAM loaders do.
  - Switching changes the code under the CPU, so module code switches
    banks from main RAM (copy a trampoline there) or from code that is the
    same in both banks. Mind the reads the CPU makes: an indexed read can
    land in a switching zone, and a real NMOS 6502 also reads the byte
    after each one-byte instruction and the unfixed address of an indexed
    read, which this emulator's core does not (a test pins that an `RTS`
    at `$BFEF` does not select bank 0 here). Code that must run on a real
    machine must not end within a byte of a zone, nor index across one.
  - The MOS calls a ROM's service entry at `$8003` in whatever bank is
    selected, so a module meant for a real carrier keeps a header and a
    way back to bank 0 in every bank (the latch powers up undefined).
- **The MOS** is a 6502 ROM, `bbc_mos_rom.asm`, assembled with the
  repository's own assembler (`asm/pyasm.py`, the work-alike of `asm/17`)
  by `bbc_mos_to_c.py` into `bbc_mos_rom_generated.h`, which is checked
  in (the Makefile rebuilds it when the source changes; the end-to-end
  test checks that it matches). The entry points sit at their real
  addresses (`$FFB9` OSRDRM to `$FFF7` OSCLI, and the `$FFB6` length and
  `$FFB7` address of the default vector table), each jumping through its
  vector in page 2 as the real MOS does, so a program that replaces a
  vector, or chains to the old one, works. Reset sets the vectors,
  builds the ROM type table at `$02A1` from each slot's header (a slot is
  a ROM if `\0(C)` is at the offset given at `$8007`), selects the
  highest language ROM (`$028C`), or slot 15 if there is none, writes
  `$F4` and ROMSEL, clears the Escape flag (`$FF`), and runs the command
  or the program, with the run's end as its return address.
- **How a call reaches C (the trap)**: each default handler ends in the
  byte `$02` (a JAM opcode, which halts a real NMOS 6502) right after a
  NOP. The run loop serves it only when the instruction it has just run
  is that NOP, which happens only by falling into it from the MOS's own
  handler or by entering the handler from its vector. Reaching a trap
  byte in any other way (a `JMP` into the middle of the MOS) ends the run
  as a fault, as does a JAM opcode anywhere else; no write to any
  address and no opcode outside the MOS can trigger a trap. The trap
  counts two cycles; the C work takes no emulated time.
- **Character I/O**: OSWRCH writes the byte to standard output unchanged
  (VDU codes pass through; OSNEWL and OSASCI's CR write `LF CR`). OSRDCH
  reads a byte from standard input; at its end it returns Escape (`A=$1B`,
  C set) and sets the Escape flag. OSWORD 0 reads a line from standard
  input without echo: a host newline ends it (stored as CR), DEL or
  backspace removes a character, characters outside the block's range and
  beyond its length are dropped; at the end of input with nothing read it
  returns Escape (C set). OSWORD 1 reads the clock, five bytes of
  centiseconds since reset, from the cycle count at 2 MHz; OSWORD 2 sets
  it. Other OSWORDs go to the ROMs as service call 8.
- **OSBYTE**: 0 (X=0: the error "OS 2.00", 247; else X=2, the B+), 126
  (acknowledge Escape), 127 (end of file X), 130 (X=Y=`$FF`), 131 (PAGE),
  132 (HIMEM), 142 (enter the language in slot X: select it, record it at
  `$028C`, enter `$8000` with A=1; an empty slot does nothing, a ROM
  without a language entry is the error "This is not a language"), 143
  (a service call: X the call, Y its argument; X=0 on return if claimed),
  170 (the ROM type table's address), 252 (the current language, `$028C`:
  X the old value, (old AND Y) EOR X the new, Y the next variable's). Any other is offered to the ROMs as
  service call 7 with A, X and Y in `$EF`, `$F0` and `$F1`; unclaimed it
  returns X=`$FF` with V set. A language never returns on a real
  machine; here the MOS enters it with the stack reset and the run's end
  as its return address, so a tool that ends either by returning from its
  service call or by OSBYTE 142 and then returning from the language ends
  the run with status 0.
- **Service calls** go to every ROM whose type has bit 7 set, slot 15 down
  to 0, each selected in `$F4` and ROMSEL, with A the call, X the slot and
  Y the argument; a ROM claims a call by returning A=0, and the slot
  selected before is selected again.
- **OSCLI** stores the line's address in `$F2/$F3` and skips spaces and
  `*`s; `|` starts a comment. Built in: `RUN name` (or `/name`): load the
  file at its load address and enter its execution address (the code's
  RTS returns to OSCLI's caller; OSARGS 1 gives the command line tail),
  `LOAD name [addr]`, `SAVE name start end|+length [exec [reload]]`,
  `HELP [arg]`: service call 9 to every ROM, with Y the offset of its
  argument (after spaces) from `($F2)`; the MOS prints nothing of its own
  (a real MOS prints its version too: memory). Anything else is offered to the ROMs as service call 4, with A=4 and Y
  the offset of the command from `($F2)`; unclaimed, a file of that name
  is run as by `*RUN`, and otherwise it is the error "Bad command" (254).
  Abbreviations (`*R.`) and the MOS's other commands (`*FX`, `*KEY`,
  `*TV`, ...) are not there.
- **The filing system** works in `--disk DIR` (without it a file call is
  the error "No disk (--disk)"). Load and execution addresses live in
  `.inf` files beside the data (`NAME LOAD EXEC [LENGTH]`, hex), as BBC
  tools write them; a file without one has zero addresses. Names are used
  as given, case and length included (no DFS seven-character limit, no
  `$.` directory), ended by CR or a space; a leading `./` (or several) is
  dropped, naming the directory itself; any other `/`, and `..`, is the
  error "Bad name". OSFIND opens (`$40` input, `$80` output, `$C0` update)
  up to 15 files, handles `$11`-`$1F`, and returns 0 for a file that
  can't be opened; A=0 closes Y (0: all). OSBGET returns C set and
  `A=$FE` at the end of the file and the error "EOF" on reading again
  there; OSBPUT to a file opened for input is the error "Read only".
  OSARGS: Y=0 A=0 the filing system (4, the DFS's), A=1 the command line
  tail's address, A=`$FF` flush; Y a handle: read PTR, write PTR, read
  EXT, flush. OSGBPB 1-4 (C set when the count is not used up; A=0).
  OSFILE `$FF` load (at the block's address if its execution address's
  low byte is 0), 0 save (writing the `.inf`), 1-4 write catalogue
  information (4 is accepted and ignored), 5 read it, 6 delete; a missing
  file is an error only for load. Errors use the DFS's numbers.
- **Errors** are raised as the MOS raises them: a BRK followed by the
  number and a zero-terminated message. The BRK handler, as MOS 1.20's,
  sets `$FD/$FE` to the error number, `$024A` to the ROM selected, `$F0`
  to the stack pointer, offers service call 6, selects the language ROM
  again and jumps through BRKV. The default BRKV handler prints the
  message (read from the ROM that raised it, if it is in the window) to
  standard error and ends the run with status 1.
- **Not in this MOS**: interrupts of any kind (no 100 Hz tick, no
  vertical sync, no events; IRQ1V and IRQ2V exist and are never
  entered), the screen and VDU drivers, the keyboard and its buffer,
  `*FX`, GSINIT/GSREAD, OSEVEN and VDUCHR (they raise the error 255 "Not
  in this emulator's MOS"), FSCV (its default just returns), service calls
  1 and 2 (workspace claims) and the others the MOS issues at reset,
  duplicate-ROM detection, printing the language's title, the Tube, and
  `--input`/`--output` (standard input and output are used).

### Checks

Two things a real MOS punishes are counted and shown by `--exit-report`;
`--bbc-strict` ends the run at the first with a message and status 1:

- writes by code outside the MOS (any PC outside `$C000-$FBFF` and
  `$FF00-$FFFF`) to memory the MOS owns: zero page `$90-$FF` except `$F4`
  (the ROMSEL copy, which code paging a ROM writes), `$F6/$F7` (OSRDRM's
  input pointer) and `$A8-$AF` (documented as workspace for * commands);
  `$0200-$03FF` except the vectors (`$0200-$0235`, which programs may
  replace) and the ROM type table (`$02A1-$02B0`, which sideways RAM
  loaders write); and `$0800` up to PAGE. `$0400-$07FF` (the language's
  workspace), the stack and the rest of RAM are not checked. The MOS's own
  writes, and the C side's, are not checked.
- a ROMSEL value that differs from `$F4` when code outside the MOS calls a
  MOS entry point.

## wendy2c demo

`emulator/demo_wendy2c.sh` is the end-to-end smoke launch. It:

1. Assembles `firmware/boards/wendy2/upload_and_run_eeprom_wendy2c.s`
   into a boot ROM.
2. Assembles a payload (default
   `firmware/programs/wendy2/hello_ram_4000_wendy2c.s`; override via
   `DEMO_PAYLOAD=...`).
3. Frames the payload (length + bytes + BSD checksum) using
   `wendy2_upload.py`.
4. Runs the emulator with the framed bytes pre-queued so the boot ROM
   uploads them into RAM, jumps to `$4000`, and the payload writes to
   the LCD.

Cycle cap default is 3,000,000 oscillator ticks (~150 ms wallclock).
Override with `DEMO_CYCLE_CAP=<N>`. The script fails fast if any
vasm invocation errors — older vasm releases that don't recognise
flags like `-ignore-mult-inc` will abort cleanly. It also takes `--web`
(browser UI), `--audio` and `--wav PATH`; see its header.

Pass `--live` to launch straight into the live render instead:

```sh
bash emulator/demo_wendy2c.sh --live
DEMO_PAYLOAD=firmware/programs/wendy2/wendy2c_led_test.s bash emulator/demo_wendy2c.sh --live
```

`--live` runs uncapped (`DEMO_CYCLE_CAP` still overrides if you want a
fixed-length recording); `q` / `ESC` / `Ctrl-C` in the panel quits.

### Uploading to a running emulator

`wendy2c_emu_serve.sh` starts the emulator with the boot ROM and a
`--serial-link` socket (`--live` by default, or `--web`), like plugging
in the real board. In another terminal,
`compile_and_upload_wendy2c_emu.sh foo.s` assembles, frames and uploads a
program through `wendy2c_emu_upload.py` and `wendy2c_emu_link.py` (the
emulator-side counterparts of `tools/upload/`).

## `--web` mode

`--web` serves the board on `http://127.0.0.1:8080/` (`--web-port`,
`--web-bind`): the LCD drawn dot by dot (CGRAM included), the LEDs, a
reset button, the VIA's port pins and the clock, updated about 30 times
a second. A program's STP stops only the CPU: the board runs on (as it
does under `--live`) until the reset button starts it again; a plain run
ends at STP. The status line shows the emulated clock's measured rate
against the board's (red below 98%: the host isn't keeping up, and the
audio breaks up). It runs uncapped and paced to the board's clock (or `--mhz`)
until Ctrl-C. The page (`web/index.html`) shows the machine the server
names, and an open page that reconnects to a different machine on the
same port rebuilds itself for it; `web/README.md` has the files and the
protocol.

- **wendy2c**: the 16x2 LCD (or `--lcd-panel 16x1-5x10`), the LEDs on
  PB6 and PA2, the control button (SPACE holds it, R resets), and the
  PB7 piezo as audio. `emulator/demo_wendy2c.sh --web` boots a demo.
- **michael**: the 20x4 LCD, the graphic display (the ILI9341 Michael
  drives through the FPGA bus, in raw mode or the FPGA's text mode, its
  hardware scroll and backlight included) and the LED on PA1 (lit while
  PA1 is high, as on the board). Keys typed or pasted on the page go to the PS/2
  keyboard, encoded as `--keys` encodes a terminal's (`ps2_keys.h`): text, Enter, Backspace, Tab, Esc, the
  arrows, Home/End/PgUp/PgDn/Insert/Delete and Ctrl+letter.

`emulator/compile_and_run.sh --wendy|--michael <program.s> [emulator options]`
assembles a program and runs it on the board, uploaded through the board's
ROM loader as `tools/upload/compile_and_upload_<board>.sh` sends it to the
real one (so a Michael program needs a `start` label). It serves the page
unless the options say `--live` or `--cycle-cap` (headless, with
`--exit-report` to show the LCD); options after the program go to the emulator.

```sh
# either board: assemble, upload through its ROM's loader, serve the page
emulator/compile_and_run.sh --michael firmware/programs/michael/michael_graphic_keyboard.s
emulator/compile_and_run.sh --wendy firmware/programs/wendy2/hello_ram_4000_wendy2c.s --web-port 8081

# michael: a program loaded into RAM (the keyboard echo demo)
firmware/vasm -wdc02 -Fbin -dotdir -ignore-mult-inc -esc \
    -o /tmp/kbd.bin firmware/programs/michael/michael_keyboard_new.s
emulator/emulator.out /tmp/kbd.bin --machine michael --load 2000 --web

# michael: the editor, through the ROM's loader
editor/bin/editor-michael.sh --web
```

## `--live` mode

`--live` on wendy2c (michael's `--live` shows just the LCD) enters an ANSI alternate-screen and renders
every ~30 ms:

```
  LCD:
  +----------------+
  |Hi! I'm Wendy 2.|
  |0042            |
  +----------------+

  LED PB6: [*]   LED PA2: [ ]   BTN PA1: [ ]   (SPACE)

  PORTA bits:     1   0   1   0   0   1   1   0    DDRA=$FF
                 D7  D6  D5  D4  RW LED BTN  RS

  PORTB bits:     0   1   0   0   0   1   0   1    DDRB=$3F
                 T1 LED   E  B4  B3  B2  B1  B0

  osc:8200000  cpu:4087045  pc:$402E  irq:0
```

Keys:
- `q` / `ESC` / `Ctrl-C` — quit (terminal contents are restored)
- `SPACE` — toggle the control button (drives PORTA bit 1)
- `R` — pulse RES

Default live pacing matches the real wendy2c board: 19.44 MHz OSC
(9.72 MHz CPU after the 22V10 divide), derived from
`firmware/boards/wendy2/base_config_wendy2c.inc`'s `CLOCK_FREQ_KHZ = 9720`. Override with
`--mhz N`, where N is the OSC (crystal) frequency in MHz. `--mhz`
also throttles non-live wendy2c runs (which otherwise run at full
host speed); requesting a rate higher than the host can sustain
just runs at host speed.

The alternate-screen save/restore plumbing is shared with `--console`
and `--terminal` via `tty_alt_screen.{c,h}`.

## File layout

```
emulator/
├── emulator.c              main + nmos-default port interception + --server
├── cli.{c,h}               argument parsing + usage
├── emu_run.{c,h}           emu_run_default loop (nmos-default)
├── emu_wendy2c.{c,h}       wendy2c machine: chip wiring, run loops, --live renderer
├── emu_michael.{c,h}       michael machine: chip wiring, run loops, --live renderer
├── emu_bbcbplus.{c,h}      bbcbplus machine: slots, module and program from the options, --exit-report
├── bbc_mos.{c,h}           bbcbplus: the CPU on the B+ map, the MOS's traps and calls, the checks
├── bbc_mos_rom.asm, bbc_mos_to_c.py, bbc_mos_rom_generated.h
│                           bbcbplus: the MOS ROM's source, its generator, the generated header
├── bus.{c,h}               chip vtable + bus walk
├── cpu_core.{c,h}          fake6502-derived CPU; NMOS + 65C02 variants
├── stubs.{c,h}, file_io.{c,h}, console.{c,h}, direct_io.{c,h}
│                           nmos-default $F006 services, file ports, console/terminal UI
├── tty_alt_screen.{c,h}    alt-screen + raw termios save/restore
├── trace.{c,h}             E6502_TRACE ring buffer / histogram
├── pace.{c,h}, lcd_report.{c,h}, ps2_keys.{c,h}
│                           wall-clock pacing, --lcd-trace output, PS/2 scan codes
├── audio.{c,h}             PB7 -> WAV / miniaudio live playback (vendor/miniaudio.h)
├── serial_link.{c,h}       --serial-link socket transport
├── web_server.{c,h}, web_json.{c,h}, web_run.{c,h}, web_display.{c,h}, web/
│                           --web server, its JSON parser, the shared --web
│                           run loop, the graphic display's deltas, the browser UI
├── chips/                  chip models (see chips/README.md)
├── pld_to_c.py             22V10 .pld -> chips/clock_22v10_pld_generated.h
├── persistent_emulator.py  --server wrapper the Python tests use
├── demo_wendy2c.sh, wendy2c_emu_serve.sh, compile_and_upload_wendy2c_emu.sh,
│   wendy2_upload.py, wendy2c_emu_upload.py, wendy2c_emu_link.py
│                           demo and upload tooling for the emulated wendy2c
├── tools/                  HD44780 font extraction
├── tests/                  see tests/README.md
└── vendor/                 miniaudio
```

## wendy2c memory map

Decoded by `22V10-wendy2c.pld` (emulated in `chips/clock_22v10.c` via
the generated `clock_22v10_pld_generated.h`). The config is `C4..C0` =
VIA `PB4..PB0`; it reads as `$00` after reset because DDRB is 0.

Wiring:

- ROM (28C256, 32 KiB) sees CPU `A14..A0`, so ROM offset = address & `$7FFF`.
- RAM (512 KiB) sees `R18..R15` from the PLD on its `A18..A15`, CPU `A15`
  on its `A14`, and CPU `A13..A0`. CPU `A14` goes only to the PLD.
  Physical = `R << 15 | A15 << 14 | A13..A0`.
- `/RAMCS` is asserted whenever `/ROMCS` and `/VIACS` are not.
- CK runs at half speed while ROM is selected.

Per config (RAM entries are the physical address of the region's first
byte; `n` = `C3..C0`, `m` = `C2..C0`):

| Config        | `$0000-$3FFF`  | `$4000-$7FFF` | `$8000-$BFFF`       | `$C000-$EFFF`       | `$F000-$F7FF` | `$F800-$FFFF` |
|---------------|----------------|---------------|---------------------|---------------------|---------------|---------------|
| `$00`         | `$08000`       | `$00000`      | ROM `$0000`         | ROM `$4000`         | VIA           | ROM `$7800`   |
| `$01-$0F`     | `n * $8000`    | `$00000`      | `$04000`            | `$0C000`            | VIA           | `$0F800`      |
| `$10`         | `$08000`       | `$00000`      | ROM `$0000`         | ROM `$4000`         | VIA           | `$0F800`      |
| `$18`         | `$10000`       | `$00000`      | ROM `$0000`         | ROM `$4000`         | VIA           | `$0F800`      |
| `$11-$17`     | `$08000`       | `$00000`      | `m * $10000 + $4000`| `m * $10000 + $C000`| VIA           | `$0F800`      |
| `$19-$1F`     | `$10000`       | `$00000`      | `m * $10000 + $4000`| `m * $10000 + $C000`| VIA           | `$0F800`      |

In words:

- `$4000-$7FFF` is common RAM and `$F000-$F7FF` is the VIA (16
  registers on `A3..A0`, mirrored) in every config. `$F800-$FFFF` is
  common RAM in every config except `$00`, where it is ROM.
- Configs `$01-$0F` give 60 KiB of flat RAM; only the lower window
  (which holds zero page and the stack) switches, across banks 1-15.
  `$00` and `$01` share lower bank 1.
- With `C4` set, `C3` picks lower bank 1 or 2 and `C2..C0` picks the
  upper window: `0` maps ROM (`$10`, `$18`), `1-7` map a 28 KiB RAM
  upper bank.

Physical RAM, in 16 KiB halves of 32 KiB bank `k`:

| Physical                        | Reached from                                          |
|---------------------------------|-------------------------------------------------------|
| `$00000-$03FFF`                 | `$4000-$7FFF`, all configs                            |
| `$04000-$07FFF`                 | `$8000-$BFFF`, configs `$01-$0F`                      |
| `$08000-$0BFFF`                 | lower bank 1                                          |
| `$0C000-$0EFFF`                 | `$C000-$EFFF`, configs `$01-$0F`                      |
| `$0F800-$0FFFF`                 | `$F800-$FFFF`, all configs except `$00`               |
| `k * $8000 + $0000-$3FFF`, k≥2  | lower bank `k`                                        |
| `k * $8000 + $4000-$7FFF`, k≥2  | upper bank `m = k / 2` (`$C000` half when `k` is odd) |

Lower banks only ever use the low half of a 32 KiB bank and upper
windows only the high half, so the two windows never alias. Never
reachable: `$0F000-$0F7FF` and `m * $10000 + $F000-$FFFF` for
`m = 1-7` (30 KiB in total). `tests/test_pld_config_map.c` pins these
mappings, including that all 32 configs are distinct.

## Testing references

- **Klaus Dormann's** 6502 functional tests — `tests/dormann/`. Build the
  binaries there with `make` (needs cc65); `tests/test_dormann.c` runs them
  for the NMOS and 65C02 variants and reports SKIP until they exist.
- **Tom Harte's ProcessorTests** — `tests/harte/`. Fetched on demand
  via `tests/harte/fetch.sh`. `make harte` runs them when the data is
  present; otherwise prints a warning and exits 0.
- **Everything else** — `tests/README.md`.
- **wendy2c goldens** — `tests/wendy2c_goldens.sh`. Builds and
  uploads real wendy2c programs through the boot-ROM upload protocol
  and checks the resulting LCD frame.

## See also

- `chips/README.md`, `tests/README.md`, `web/README.md`,
  `tools/README_hd44780_font.md` — the chip models, the test suites, the
  browser UI and the font extraction tool.
- `WENDY2_EMULATOR_PLAN.md` — the phase-by-phase plan for the wendy2c
  machine (done through phase 13, plus 16-17; phase 14, the ST7920 stub,
  and phase 15, bus-trace mode, snapshots and `--selftest`, were never
  built), with the design rationale for the bus / chip-vtable layout and
  cycle pacing.
- `INVESTIGATION-wendy2c.md` — pre-phase-0 notes on the 22V10 PLD
  decode, serial RX timing, RAM bank ordering, and LCD pin map.
- `NOTES-bbcbplus.md` — the facts about the real B+128 and its MOS that
  the bbcbplus machine relies on, each marked checked (and against what)
  or from memory.
- `NOTES-timing-accuracy.md` — where CPU and VIA cycle timing still
  differs from the W65C02S / W65C22 (instruction-atomic CPU, free
  interrupt entry, SR-under-T2 shift rate, unmodelled VIA features)
  and how to fix each.
- `NOTES-web-audio-drift.md` — how web audio was scheduled, and the
  jitter buffer and drift correction that replaced it.
