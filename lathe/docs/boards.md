# Running on the boards

A Lathe program can run on four machines of the emulator (`../../emulator/README.md`): the default machine, Michael, Wendy 2, which can also be run with files (`wendy2disk`), and the BBC Model B+128 (`bbc`). Each has an environment file in `../env/`. This document gives the recipe for each: how the emulator is run, the memory map, what the file must hold, how output is read, and how a timer interrupt is set up.

`build.py --env NAME --run` follows these recipes. What the driver knows about each board is in `../host/driver/boards.py`.

The facts here come from a research run that put raw asm17 programs on the boards without a vasm-built ROM. The vasm firmware in `../../firmware/` is not needed.

## The default machine

The emulator's `nmos-default` machine: an NMOS 6502 with 64 KB of flat RAM and host services. Environment `host.env`.

```bash
emulator/emulator.out PROG.bin --output - --no-dump
```

| Item | Value |
|---|---|
| CPU | NMOS 6502 |
| Code | `$0200-$BFFF` |
| Data | `$C000-$EFFF` |
| Host services | `$F006` and up (`../../asm/17/environment.asm`): read a byte, write a byte, open, close, arguments, exit |

- **The file** is an `output image`: memory from the start of the code range to `$FFFF`, with the reset vector at `$FFFC`.
- **Output** is what the program writes with the host services: `$F009` writes the byte in A to the output.
- **The end.** `exit call $F00F`: the start-up code calls `$F00F` with A = 0 when `main` returns. The exit status is A.
- **Interrupts.** This machine cannot raise a timer interrupt. It has no VIA. Only `BRK` reaches the IRQ vector at `$FFFE`.

## Michael

Michael (v2), the Ben Eater-style board: a 65C02 with 16 KB of RAM and a VIA. The emulator's `--machine michael`. Environment `michael.env`.

```bash
emulator/emulator.out PROG.bin --machine michael --load 2000 --exit-report --cycle-cap N
```

| Address | What is there |
|---|---|
| `$0000-$00FF` | Zero page, free. |
| `$0100-$01FF` | The stack. The stack pointer is not preset, so the start-up code sets it (`stack $FF`). |
| `$0200-$1FFF` | Data. |
| `$2000-$3EFF` | Code. The program is loaded at `$2000`. |
| `$3F00-$3F02` | Where the IRQ vector points. |
| `$6000` | The VIA. |

- **The file** is the code bytes from the load address, and nothing else (`output raw`). Without `--rom`, the emulator points the reset vector at the load address, so `$start` must be first.
- **The end.** The run ends at `STP` (opcode `$DB`), which `exit stop` puts after `main`, or at the cycle cap. There are no host services.
- **Output** is the 20x4 LCD. `--exit-report` prints to the error output a line `michael: exit cpu_cycles=… pc=$…. (STP)`, then `lcd:` and four lines `|....................|`. The reason in brackets is `cycle cap` when the program did not stop.
- **The LCD** is in 8-bit mode. The emulator starts it as the ROM would leave it: two lines, display on, clear.

| LCD line | Where |
|---|---|
| D0-D7 | VIA port B, `$6000` |
| RS | PA5 |
| RW | PA6 |
| E | PA7 |

Port A is at `$6001`. Its direction register `$6003` takes `$EE`, the board's outputs. Port B's direction register is `$6002`.

**A timer interrupt.** Store `JMP handler` (`$4C` and the handler's address) at `$3F00`. Then set up VIA timer 1 as below, and `CLI`.

## Wendy 2

Wendy 2 (wendy2c): a W65C02S with 512 KB of banked RAM, a VIA and a 16x2 LCD. The emulator's `--machine wendy2c`. Environment `wendy2.env`.

```bash
emulator/emulator.out PROG.bin --machine wendy2c --wendy2-prog PROG.bin --load 4000 --cycle-cap N --exit-report
```

The positional file must be given, but its content is not used: pass the program itself. `--wendy2-prog` loads the program into RAM and starts it there, skipping the serial boot. The cycle cap counts oscillator ticks, about 2 per CPU cycle.

| Address | What is there |
|---|---|
| `$0000-$00FF` | Zero page, free. |
| `$0100-$01FF` | The stack. The stack pointer is preset to `$FF`. |
| `$0200-$3FFF` | Data. |
| `$4000-$EFFF` | Code. The program is loaded at `$4000`. |
| `$F000` | The VIA. |
| `$F800-$FFFF` | RAM, the vectors included. |

- **The file** is the code bytes from the load address (`output raw`). It must stay below `$F000`.
- **The end.** The run ends at `STP` or at the cycle cap. There are no host services, but there are files with `--disk` (below).
- **Output** is the 16x2 LCD. `--exit-report` prints `exit osc_ticks=… cpu_cycles=… pc=$…. (STP)`, then `lcd:` and two lines `|................|`.
- **The LCD** is in 4-bit mode.

| LCD line | Where |
|---|---|
| D4-D7 | PA4-PA7 (port A, `$F001`) |
| RW | PA3 |
| RS | PA0 |
| E | PB5 (port B, `$F000`) |

PB0-PB4 select the memory bank and must stay `$01`. So every write to port B, such as a pulse on E, keeps those bits.

**Banking**, in three lines:

- The bank register is VIA port B, bits 0-4. The program starts with `$01`: all RAM, flat.
- The window is `$8000-$EFFF`.
- `$11` to `$17` select RAM banks 1 to 7 in the window and keep `$0000-$7FFF` the same.

The details are in `../../prog8/WENDY2_BANKING_TARGET_PLAN.md`.

**A timer interrupt.** Write the handler's address to `$FFFE` at run time. Then set up VIA timer 1 as below, and `CLI`.

### Wendy 2 with files

The emulator's `--disk DIR` adds file ports at `$F800-$F80F` to Wendy 2 (`../../emulator/chips/syscall_ports.h`); the files are those of the host directory `DIR`. Environment `wendy2disk.env`: the memory map of `wendy2.env`, and `define DISK 1`.

```bash
emulator/emulator.out /abs/PROG.bin --machine wendy2c --wendy2-prog /abs/PROG.bin --load 4000 --disk DIR --cycle-cap N --exit-report
```

The emulator changes to `DIR` before it opens the program, so the program's path must be absolute.

| Port | What it does |
|---|---|
| `$F800` write | Appends a byte to the file name. `$F801` write clears it. |
| `$F802` read | Opens the file named for reading: a handle, 1 to 16, or 0 if it failed. It becomes the current handle. |
| `$F803` read | Creates the file named for writing, the same way. |
| `$F804` write | Selects the current handle. Up to 16 files can be open at once. |
| `$F805` read | The next byte of the current file; 0 at the end. |
| `$F806` read | Bit 7 set at the end of the file, **and then the file is rewound**. |
| `$F807` write | Writes a byte to the current file. `$F808` write closes it. |
| `$F80F` write | Stops the emulator; the byte is not the process's exit status, and the report says "(cycle cap)". |

The ports are in fixed RAM, so they are reached from every bank.

`../rt/disk.lth` gives a Lathe program the interface of `../rt/host.lth` over the ports (the functions `../src/sys.lth` uses): `open`, `open_out`, `read` (the carry set at the end), `write`, `close`, `argc`, `argv`, `put_byte`, `put_error`, `exit`. Every call selects its handle, so many files can be open together; `read` remembers that a file ended, so the rewind does not start it again. What the default machine has as a command line, an output and an exit status are files of `DIR`:

| File | Holds |
|---|---|
| `args` | The arguments, one a line, written by whoever runs the program. |
| `out` | What the program wrote with `put_byte`. |
| `errors` | What it wrote with `put_error`. Created only if it writes something. |
| `status` | `exit(code)` writes the code in decimal and a line feed, then stops with STP. No file: `main` returned, status 0. |

**Code in banks.** An environment like `wendy2disk.env` with `code $4000 $7FFF`, a `window WIN $8000 $EFFF`, `switch WIN bank $F000 $1F`, `bank WIN N $1N FILE` entries and `place` entries puts the code of the modules placed in banks of the window, with `farcall rt_bank` ([`configurations.md`](configurations.md), section 5). The linker writes each bank's file beside the image, the build copies it into `DIR`, and the start-up code loads it through the ports before `main`. `../tests/cases/e2e-config/farcall_banks.env` is one. The default machine takes overlays the same way (`switch WIN overlay`, `farcall rt_ovl`), loaded through the host services from the emulator's working directory.

`build.py --env wendy2disk --run [--disk DIR]` runs the program on `DIR` (a temporary empty directory without it), prints `out`, copies `errors` to the error output and exits with the status. `driver/boards.py` (`run_disk`) and `build.run_program(..., disk=DIR)` do the same for the tests; the cases are in `../tests/cases/e2e-wendy2disk/`.

## The BBC Micro

The emulator's `--machine bbcbplus`, a BBC Model B+128 with the DFS in mode 7, whose MOS is the emulator's own behind the documented entry points (`../../emulator/README.md`, "bbcbplus"; the facts it rests on are in `../../emulator/NOTES-bbcbplus.md`). Environment `bbc.env`. A program is run as on the real machine, by `*RUN` with its arguments on the command line, and talks only to the MOS. A banked program (`bbc-bank.env`) is below, "Banked: the module and sideways RAM"; [`bbc.md`](bbc.md) has the design.

```bash
python3 lathe/host/driver/build.py PROG.lth -o PROG --env bbc     # writes PROG and PROG.inf
emulator/emulator.out --machine bbcbplus --disk DIR --bbc-strict --bbc-command "RUN PROG ARGS"
```

`DIR` holds the program file, its `.inf` file and the files it reads and writes. `--bbc-command` gives the line to OSCLI after reset, from `$0700`, as BASIC's prompt would; the run's status is 0 when the program returns to the MOS, 1 when an error reaches the MOS's default handler (its message goes to standard error) or `--bbc-strict` catches a write to the MOS's memory. `build.py --env bbc --run [--disk DIR]` does both and prints the output (with `--disk`, the program's own name in `DIR` must be free).

| Address | What is there |
|---|---|
| `$0000-$008F` | Zero page, the language's: the linker's zero page. `$0090-$00FF` is the MOS's and the filing system's. |
| `$0100-$01FF` | The stack, the MOS's: the start-up code leaves S as `*RUN` entered it. |
| `$0200-$03FF` | The MOS's vectors and workspace. bbc.lth writes only BRKV (`$0202`), and puts it back. |
| `$0400` | Where the start-up code keeps the stack pointer (`exit return $0400`, `bbc.KEEP`). |
| `$0401-$06FF` | Variables (`more data`), used when the main range is full. |
| `$0700-$07FF` | The command line (BASIC's input buffer; the emulator's `--bbc-command`): left alone, so that the tail stays where OSARGS points while the program runs. |
| `$0800-$18FF` | The MOS's and the DFS's workspace, up to PAGE. |
| `$1900-$6BFF` | Code (`bbc.env`): the file is loaded at PAGE, `$1900`, and entered there. |
| `$6C00-$7BFF` | Variables, up to HIMEM in mode 7 (`$7C00` is the screen). |
| `$8000-$BFFF` | The sideways ROM or RAM in the window; `$C000-$FFFF` the MOS. |

- **The file** is the code bytes from `$1900` (`output raw`). The build writes `NAME.inf` beside it (`NAME 00001900 00001900 LENGTH`), which gives `*RUN` the load and execution addresses; the driver copies both into `DIR` under the program's name without its extension, and takes them away after the run.
- **The split** between code and variables is fixed by the environment file: `bbc.env` gives 21,248 bytes to code and 4,096 to variables, with 767 more at `$0401-$06FF`, which every end-to-end case fits. A program with more variables needs its own file, as `../src/compiler-bbc.env` (code `$1900-$51FF`, variables `$5200-$7BFF`) is for the compiler's test programs.
- **The arguments** are the tail of the command, read with OSARGS (A=1, Y=0), as a real BBC gives it to a program run with `*RUN NAME ARGS`. `bbc.lth` splits it at spaces; `"..."` is one argument, which may be empty or hold spaces, with `""` for a quote inside it. The driver quotes an argument only when it must. A line holds at most 254 characters, CR not among them.
- **Output** is OSWRCH, and standard input OSRDCH; in the emulator they are its standard output and input.
- **The line end.** The BBC ends a line with CR (`$0D`): the Return key gives CR, and OSNEWL writes LF CR, which the screen needs (LF moves down, CR back to the start). A Lathe program writes and reads LF (`$0A`). So `put_byte(10)` is OSNEWL (LF CR), every other byte is written as it is, and `read_byte` gives a CR from the keyboard as LF. The driver gives each LF CR of the emulator's output back as LF, so that it compares with the default machine's. Files are never translated: `read` and `write` (OSBGET, OSBPUT) move bytes exactly, so object files and binary data copy as they are.
- **Error output** goes where output goes: the BBC has no second stream. The driver's error output is only a MOS error's message.
- **The end.** `main` returning, or `exit(0)` from any depth, returns to the MOS: the start-up code begins with `TSX` / `STX $0400`, and `exit` puts S back from there and returns. `exit(N)` with N not 0 raises a MOS error: BRK, the error number N and the message `Exit N`. The emulator prints the message and ends with status 1, and the driver gives N back as the status; a real BBC's language (BASIC) reports it as any error, with `ERR` = N. Both forms close every file first (OSFIND 0 with Y=0, as `CLOSE#0`). There is no exit status on the BBC: an error is the least that is honest.
- **Files.** OSFIND with the name ended by CR. A missing file is 0, as the MOS gives it; an error the filing system raises instead (`Bad name`, `Too many open files`) is caught for the call through BRKV and is 0 too, so that `open` keeps host's contract. At the end of a file `read` gives the carry set, and keeps giving it without calling OSBGET again, which would raise the error `EOF`. Names are passed as they are: the emulator takes any name without `/` or `..` (a leading `./` is dropped); a real DFS takes seven characters and uses `.` for its directory.
- **The program's memory only.** Every run in the tests uses `--bbc-strict`, which stops a program at its first write to memory the MOS owns.

How the interface of `../rt/host.lth` is given (`../rt/bbc.lth`):

| host.lth | The MOS |
|---|---|
| `put_byte`, `put_error` | OSWRCH; `$0A` is OSNEWL. Both are asm functions with the character in A, as host's, so asm can call them. |
| `read_byte` | OSRDCH. CR is given as LF; an error or Escape (the emulator gives Escape at the end of its input) is the end, and Escape is acknowledged with OSBYTE 126. |
| `open`, `open_out` | OSFIND `$40`, `$80`; an error is caught and is 0. |
| `read`, `write`, `close` | OSBGET, OSBPUT, OSFIND 0. |
| `argc`, `argv` | The tail from OSARGS 1, split again at each call (it stays at `$0700`). |
| `exit` | OSFIND 0 with Y=0; then RTS with the kept S, or BRK `N` `Exit N`. |

`../src/sys.lth` uses `bbc` with `define PORTS 2`, and a program that imports `host` gets `../rt/bbc/host.lth` (`boards.py`, `rt`: `build.py` looks in that directory before `../rt/`), host's functions over bbc, so a program written for the default machine, such as the end-to-end cases, runs on the BBC as it is. `bbc.lth` has no initial values, so it adds no `$init` to the other machines' builds, where `sys` imports it unused.

What a byte costs through the MOS, in this emulator (2026-11-14): `bbc.read` 70 cycles, `bbc.write` 38, `put_byte` 31; a byte copied through `sys.read` and `sys.write` with `copytest`'s loop, 141. The emulator's MOS answers a call in 2 cycles of its own, so these are a floor: a real MOS and DFS take far more for each byte, and a real disc much more again.

### Banked: the module and sideways RAM

Environment `bbc-bank.env` (stage 12, step 3; [`bbc.md`](bbc.md), "Step 3, as built"): `bbc.env`'s machine with the window `$8000-$BFDF` switched by `../rt/rt_bbc.lth`. Code goes in banks of the **module**, in its developer's form, which holds RAM; regions go in **sideways RAM** slots. The program is still run by `*RUN`, and its start-up code loads each bank's file into the module, or into a sideways slot, from the disc.

```bash
python3 lathe/host/driver/build.py PROG.lth -o PROG --env PROG.env   # PROG, PROG.inf, the bank files
emulator/emulator.out --machine bbcbplus --disk DIR --bbc-strict \
    --bbc-module-ram --bbc-module-scheme direct16 --bbc-module-slot 4 --bbc-command "RUN PROG ARGS"
```

`DIR` holds the bank files beside the program. `build.py --run` does both (`boards.module_options`: the module's options for any environment of the BBC that places code or a region in the window, with the slot from its `define MODULE_SLOT`).

- **The environment.** `bbc-bank.env` is the machine; a program adds its own `bank`, `place` and `region` lines after it. A bank's value is `$80 + n` for bank n of the module (numbered `N = n`, and 16 for bank 0, by convention) or the slot's number for a sideways slot (numbered `20 + s`: 32 and 33 for slots 12 and 13). `switch WIN bank farcall`: no register describes the switch, so the far-call module alone does (`configurations.md`, "The environment file").
- **The module's slot** is `define MODULE_SLOT 4`, which must be the emulator's `--bbc-module-slot` (4 is its default). The same objects linked for the ROM form (below) take the slot the MOS gives instead.
- **The window ends at `$BFDF`**: a read of `$BFF0+n` latches the module's bank n, and a real NMOS 6502 reads the byte after a one-byte instruction, so nothing is placed in the last 32 bytes.
- **Sideways RAM** is slots 0, 1, 12 and 13 (`--bbc-sideways-ram`, the B+128's by default). A region of variables needs no file; one with constants is loaded from its file at start-up.
- **Variables of a module placed in a bank** are at the bank's top, in the module's RAM. In the ROM form (below) the banks are `rom`, and the linker puts them in main RAM.
- **The MOS is called from anywhere**: from code in a bank of the module, and inside a `with` block with a sideways slot in the window. Every switch writes `$F4` before ROMSEL, and `bbc.lth`'s catching of a filing system error selects again the slot that was in the window, which the MOS's BRK handler replaced with the language's.

| `$8000-$BFDF` | What is there |
|---|---|
| bank n of the module (value `$80 + n`) | Code and constants of the modules placed there, from `$8000`; their variables from `$BFDF` down. Its file is the bytes from `$8000` to the last placed. |
| sideways slot s (value s) | A region: its constants from `$8000` (in its file), its variables from `$BFDF` down. |

### The ROM module

A banked program, or several, as one **module image**: sixteen 16 KB banks (262,144 bytes, scheme `direct16`) in one sideways slot, each program started by a `*` command of its own with its arguments, its code banks read only, its regions in sideways RAM and the rest in main RAM ([`bbc.md`](bbc.md), "Step 3, as built: the ROM form", has the layout and the start and end sequences).

**Build.** Each program is linked on its own with a ROM environment: `../env/bbc-rom.env` with its lines, which `bbcrom.rom_env` makes from its `bbc-bank.env` lines (the window `$8050-$BFDF`, its banks of the module numbered from a first bank and `rom`; it returns the next number, for the next program). Then the image tool puts the links together:

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, 'lathe/host/driver')
import bbcrom
n = bbcrom.rom_env('first-run.env', 'first-rom.env', 1)     # banks 1, 2, 3 ...
bbcrom.rom_env('second-run.env', 'second-rom.env', n)       # ... and on
EOF
python3 lathe/host/driver/build.py first.lth -o rom1/FIRST --env first-rom.env --keep rom1/work
python3 lathe/host/driver/build.py second.lth -o rom2/SECOND --env second-rom.env --keep rom2/work
python3 lathe/host/driver/bbcrom.py -o MODULE --listing MODULE.txt --loader disk/LOADMOD \
    FIRST=rom1/FIRST,first-rom.env,rom1/work/first.map SECOND=rom2/SECOND,second-rom.env
```

`bbcrom.py` takes each program's resident image (build.py's output, from the start of its `code` range), its bank files beside it, its environment and, for the listing, its map; it writes the image and the listing (what is in each bank, what each command copies where, the space left), and with `--loader` the developer's loader `LOADMOD` and its `.inf`. It fails with a message naming the program and the bank when something does not fit or collides: two programs in one bank, a bank of the module not `rom`, bank 0 (the module's own), the window not `$8050-$BFDF`, a region not in sideways RAM, a range over `$0700-$07FF`, more resident parts and region constants than the free banks hold. The tests call `bbcrom.image(specs, out, listing)` and `bbcrom.loader(out)`.

**Run it from ROM**:

```bash
emulator/emulator.out --machine bbcbplus --disk DIR --bbc-strict \
    --bbc-module MODULE --bbc-module-scheme direct16 [--bbc-module-slot S] [--bbc-module-bank B] \
    [--bbc-rom 15=LANG.rom] --bbc-command "FIRST ARGS"
```

**Run it in the developer's form**: the module holds RAM, empty; `LOADMOD` fills it from the image file on the disc and enters it in the ROM type table, then the command runs as from ROM (`--bbc-command` is repeatable: each line runs when the one before returns):

```bash
cp MODULE DIR/MODULE; cp disk/LOADMOD disk/LOADMOD.inf DIR/
emulator/emulator.out --machine bbcbplus --disk DIR --bbc-strict \
    --bbc-module-ram --bbc-module-scheme direct16 --bbc-module-slot 4 \
    --bbc-command "RUN LOADMOD MODULE 4" --bbc-command "FIRST ARGS"
```

`boards.run_module(board, image, disk, command, args, slot=, bank=, ram=, before=, roms=)` does both for the tests (`before` is the loader's line, `roms` a language ROM).

- **The arguments** are the command's tail, which the module copies to `$0700` (at most 239 bytes); `bbc.lth` reads it there when the program was started by the module (`bbc.from_rom()`), and from OSARGS for `*RUN`. The same objects link both ways.
- **The end**: status 0 enters the current language again with OSBYTE 142 if it is a language ROM, and otherwise returns from the service call, claimed (the emulator without `--bbc-rom` has no language: the run ends with status 0). A status N other than 0 is the MOS error `Exit N`, as for `*RUN`.
- **`*HELP`** lists the module's commands; a command it does not know is left to the other ROMs and the MOS (`Bad command`).
- **Sideways RAM**: the slots the program's regions are in are taken; their constants are copied there from the image at the command.

### The compiler on the BBC

The Lathe-written compiler at its full capacities, `../src/lathec-bbc.env` ([`bbc.md`](bbc.md), "Step 4, as built"): five banks of the module, its tables in the four sideways RAM slots. Build the image with the compiler in it, and the loader (`rom/` must exist):

```bash
python3 -c "import sys; sys.path.insert(0, 'lathe/host/driver'); import bbcrom; \
    bbcrom.rom_env('lathe/src/lathec-bbc.env', 'rom/lathec.env', 1)"    # banks 1 to 5, rom
python3 lathe/host/driver/build.py lathe/src/lathec.lth -o rom/LATHE --env rom/lathec.env --keep rom/work
python3 lathe/host/driver/bbcrom.py -o MODULE --listing MODULE.txt --loader DIR/LOADMOD \
    LATHE=rom/LATHE,rom/lathec.env,rom/work/lathec.map
```

Then compile a module in `DIR`, which holds its source and the interfaces of what it imports, with `*LATHE` and the compiler's usual command line ([`../host/README.md`](../host/README.md), "Command lines"); the output directory `.` is the disc itself (the emulator drops a leading `./` from a name):

```bash
emulator/emulator.out --machine bbcbplus --disk DIR --bbc-strict \
    --bbc-module MODULE --bbc-module-scheme direct16 --bbc-command "LATHE OPTIONS NAME.lth ."
```

From the module's RAM form: `--bbc-module-ram`, and `--bbc-command "RUN LOADMOD MODULE"` before the command, with `MODULE` copied to `DIR`. The developer's form without an image: `build.py lathe/src/lathec.lth -o lathec.bin --env lathe/src/lathec-bbc.env`, run with `*RUN LATHEC ARGS` as "Banked" above has it, the five bank files and `LATHE33.BIN` beside it. `../tests/test_bbc_selfhost.py` does all three; `test_src_lathec.py`'s `OnTheBBC` runs the corpus so (`LATHE_LATHEC_BBC=1`).

- **Files** are named as the emulator's directory takes them, with no directories: an import directory other than `.` cannot be reached (the corpus's two inputs that use one cannot give the host's output).
- **The command line** is at most 239 bytes after `LATHE `.
- **Memory**: `*LATHE` takes zero page `$00-$8F`, `$0400-$07FF` and `$1900-$7BFF` as it finds them, and the four sideways RAM slots; nothing in the compiler relies on memory being 0 (the test fills it first).

### The tool chain on the BBC

The compiler and the linker in one image, `*LATHE` and `*LLINK` ([`bbc.md`](bbc.md), "Step 5, as built"): a program is compiled, linked and run on the BBC. Build the image (`rom/` must exist):

```bash
python3 -c "import sys; sys.path.insert(0, 'lathe/host/driver'); import bbcrom; \
    n = bbcrom.rom_env('lathe/src/lathec-bbc.env', 'rom/lathec.env', 1); \
    bbcrom.rom_env('lathe/src/linker-bbc.env', 'rom/linker.env', n)"     # banks 1-5, 6-10
python3 lathe/host/driver/build.py lathe/src/lathec.lth -o rom/LATHE --env rom/lathec.env --keep rom/lathe
python3 lathe/host/driver/build.py lathe/src/link.lth -o rom/LLINK --env rom/linker.env --keep rom/llink
python3 lathe/host/driver/bbcrom.py -o MODULE --listing MODULE.txt --loader DIR/LOADMOD \
    LATHE=rom/LATHE,rom/lathec.env,rom/lathe/lathec.map LLINK=rom/LLINK,rom/linker.env,rom/llink/link.map
```

`DIR` holds the program's sources (its own modules, and those of `lathe/rt/` it needs under their base names: `lathe/rt/bbc/host.lth` as `host.lth`, `bbc.lth`, `lathe/src/sys.lth`, `rt_math.lth`...) and its environment file (`lathe/env/bbc.env`). Compile each module, in the order `build.py` does (a module after those it imports, then the run-time modules the code calls), with the options `build.py` gives for the environment (`-c6502 -dBOARD=3 -dPORTS=2`, and `-dNAME` for each `define`); link the objects, the main module's name second; give the image its addresses; run it:

```bash
emulator/emulator.out --machine bbcbplus --disk DIR --bbc-strict \
    --bbc-module MODULE --bbc-module-scheme direct16 \
    --bbc-command "LATHE -c6502 -dBOARD=3 -dPORTS=2 bbc.lth ." \
    --bbc-command "LATHE -c6502 -dBOARD=3 -dPORTS=2 host.lth ." \
    --bbc-command "LATHE -c6502 -dBOARD=3 -dPORTS=2 hello.lth ." \
    --bbc-command "LLINK bbc.env hello HELLO HELLO.map bbc.lo host.lo hello.lo" \
    --bbc-command "LOAD HELLO 1900" --bbc-command "SAVE HELLO 1900 +25 1900" \
    --bbc-command "RUN HELLO"
```

- **The texts of the errors.** The tools' ROM forms hold no texts of their errors: the module image holds them (`bbcrom.py` packs them into every image from the host's tables) and writes them, so an error reads as on the host with nothing on the disc. Only if no ROM answers the module's service call (`$4C`) is an error its number alone with the rest of the line (`hello.lth:3:3: error 40`), whose text `../host/err.py` and `../host/lk_err.py` list ([`bbc.md`](bbc.md), "The texts in the module"). The developer's forms (`*RUN LATHEC`, `*RUN LLINK`) hold their texts.
- **The link's command line** is `LLINK ENV MAINMODULE IMAGE MAP OBJECT...` ([`../host/README.md`](../host/README.md), "Command lines"), at most 239 bytes after `LLINK `; the environment file is read from the disc. On an error the linker prints `link error N: ...` and ends with the MOS error `Exit 1`.
- **The image's addresses**: the linker writes the bytes from the start of the `code` range (`output raw`), not a catalogue entry, so `*LOAD` it at the start of `code` (`$1900` for `bbc.env`) and `*SAVE` it again with its length (the map's last code line, or `*INFO`) and that address as the execution address; `*RUN` then runs it.
- **A banked program** (`bbc-bank.env` and its lines): its bank files are written beside the image, and its start-up code loads them into the module's RAM form, so run the tools from the RAM form (`--bbc-module-ram`, `--bbc-command "RUN LOADMOD MODULE"` first): the program's banks then replace the tools' banks of the same numbers, and the tools must be loaded again after it.
- **Capacities**: the BBC's (`define LKSMALL 2` in `../src/linker-bbc.env`): 448 functions, 2,400 slots, 2,000 calls, 472 nodes; every program of the corpus but `for_ranges` (link error 10), and the compiler's test programs up to `outtest`.
- **Memory**: `*LLINK` takes zero page `$00-$8F`, `$0400-$07FF`, `$1900-$7BFF` and sideways slot 0; it runs on what the compiler left, and a program run after it on what the linker left: no variable starts as 0 unless it has that initial value (`language.md`, "Declarations"; `../tests/test_bbc_toolchain.py` runs the corpus so).

#### On a DFS disc

For a real DFS, or the emulator with `--bbc-fs dfs`, build the tools and the program with `define BBCFS 1` ([`bbc.md`](bbc.md), "File names on the BBC"): every file name the tools give is then mapped to a DFS name when it is opened, and the command lines stay as above.

- **The tools**: in copies of `lathec-bbc.env` and `linker-bbc.env`, `define BBCFS 1` for `define BBCFS 0`; in the linker's, also move the split up 16 bytes (`code $1900 $3A2F`, `data $3A30 $7BFF`), as `../tests/test_bbc_dfs.py` (`dfs_env`, `LINKER_ROOM`) does. Then `rom_env` and the rest as above.
- **The program**: `lathe/env/bbc-dfs.env` in place of `bbc.env` (for a banked program, `bbc-bank.env` with `BBCFS 1`).
- **The disc**: each file under its DFS name: `hello.lth` is `L.HELLO`, `bbc-dfs.env` is `E.BBC-DFS`, and the tools write `O.HELLO`, `I.HELLO`, `M.HELLO`, `B.NAME` for a bank file `NAME.BIN`; an image (a name with no `.`) keeps its name. On the emulator a file `X.NAME` is the host file `X.NAME` in `--disk DIR`, `$.NAME` for one with no directory; drive N is `DIR/:N`. `../host/driver/bbcfs.py` gives each name (`dfs_name`) and its host file (`host_file`).
- **Drives**: a first directory `0/` to `3/` is the drive: `*LATHE hello.lth 1` writes `:1.O.HELLO` and `:1.I.HELLO` and reads interfaces there, and `LLINK bbc-dfs.env hello HELLO HELLO.map 1/bbc.lo 1/host.lo 1/hello.lo` reads the objects there. A catalogue holds 31 files.

```bash
emulator/emulator.out --machine bbcbplus --disk DIR --bbc-strict --bbc-fs dfs \
    --bbc-module MODULE --bbc-module-scheme direct16 \
    --bbc-command "LATHE -c6502 -dBOARD=3 -dPORTS=2 -dBBCFS=1 bbcfs.lth 1" \
    --bbc-command "LATHE -c6502 -dBOARD=3 -dPORTS=2 -dBBCFS=1 bbc.lth 1" ...
```

- **Limits a real disc adds**, which the emulator does not show: the linker keeps its map open while it writes the image, so a map over 16 KB stops the link with "Can't extend" (outtest's is 23 KB: make room first with `*SAVE M.OUTTEST 0 +6000`); the module image (256 KB) is larger than a side; a self-compile's files fill 4.5 sides (bbc.md, "Measured for a real disc").

#### On two ADFS discs

The compiler rebuilt from its sources on a B+128 with ADFS ([`bbc.md`](bbc.md), "ADFS"; `../tests/test_bbc_adfs.py`, `Loop`, does exactly this on the emulator). What is needed: the B+128 with ADFS 1.30 beside its DFS (PAGE `&1F00`), two 80-track double-sided drives (ADFS's drives 0 and 1, an L disc of 640 KB each), and the module's RAM form, the developer's module, in a socket (slot 4 here). Three discs: two blank ones, A and B, and C for the module image.

**On the host**, build both tools with ADFS's names and PAGE: in copies of `lathec-bbc.env` and `linker-bbc.env`, `define BBCFS 2` and `define ADFS 1` (`test_bbc_adfs.adfs_env` makes them); then the ROM environments, the image as in "The tool chain on the BBC", and LOADMOD for `$1F00`:

```bash
python3 -c "import sys; sys.path.insert(0, 'lathe/host/driver'); sys.path.insert(0, 'lathe/tests'); \
    import bbcrom, test_bbc_adfs as a; \
    a.adfs_env(a.COMPILER_ENV, 'rom/lathec-dev.env'); a.adfs_env(a.LINKER_ENV, 'rom/linker-dev.env'); \
    n = bbcrom.rom_env('rom/lathec-dev.env', 'rom/lathec.env', 1); \
    bbcrom.rom_env('rom/linker-dev.env', 'rom/linker.env', n)"
python3 lathe/host/driver/build.py lathe/src/lathec.lth -o rom/LATHE --env rom/lathec.env --keep rom/lathe
python3 lathe/host/driver/build.py lathe/src/link.lth -o rom/LLINK --env rom/linker.env --keep rom/llink
python3 lathe/host/driver/bbcrom.py -o MODULE --short MODULE.disc --listing MODULE.txt \
    LATHE=rom/LATHE,rom/lathec.env,rom/lathe/lathec.map LLINK=rom/LLINK,rom/linker.env,rom/llink/link.map
python3 -c "import sys; sys.path.insert(0, 'lathe/host/driver'); import bbcrom; bbcrom.loader('LOADMOD', 0x1F00)"
```

**From the 128 KB EPROM** ([`bbc.md`](bbc.md), "The 128 KB module"; `../tests/test_bbc_rom128.py`, `Adfs128`, does this on the emulator): number the tools' banks for an image of eight, `rom_env('rom/lathec-dev.env', 'rom/lathec.env', 0, 8)` and `rom_env('rom/linker-dev.env', 'rom/linker.env', 5, 8)` (the compiler in banks 0 to 4, the linker in 5 to 7, the `when ROM128` layouts), build as above and write the image with `bbcrom.py --banks 8 -o MODULE ...`: 131,072 bytes, the EPROM's contents (scheme `direct8`). With the EPROM in its socket, step 1 below (LOADMOD and disc C) is not needed. The texts of the errors are in the image: nothing more goes on the discs.

**The discs.** Format A and B as L discs (`*AFORM 0 L`, `*AFORM 1 L`, from ADFS's utilities disc). On A, in drive 0: `*CDIR lth` and the compiler's 25 sources as `lth.err`, `lth.kernel` and so on (from `lathe/src`, and `lathe/rt/bbc/bbcfs.lth`, `lathe/rt/bbc.lth`, `lathe/rt/disk.lth`, `lathe/rt/bbc/host.lth`, `lathe/rt/rt_math.lth`, `lathe/rt/rt_bbc.lth`, `lathe/rt/rt_frame.lth`); `*CDIR env` and the compiler's environment (`lathec-dev.env` above) as `env.lathec`; and the link's command file `LINKARG`, a word a line: `lathec.env lathec 1/LATHEC 1/LATHEC.map`, then each object as `1/NAME.lo` in the order of the compiles below. B stays blank: the tools make `lo`, `li`, `bin` and `map` on it as they write. On C: `LOADMOD` (load and execution address `1F00`) and the short image `MODULE.disc` as `MODULE`, 770 sectors.

**The session.** Every command line is the host's (`0/` and `1/` name the drives):

1. C in drive 1: `*RUN :1.LOADMOD :1.MODULE` fills the module's RAM and enters it in the MOS's table; then `*DISMOUNT 1`, B in drive 1, `*MOUNT 1`. C is not needed again while the machine is on.
2. Compile each module in `build.py`'s order (`bbcfs`, `bbc`, `disk`, `host`, `sys`, `err`, `kernel`, `fbuf`, `src`, `lex`, `out`, `typetab`, `reg`, `asmblock`, `fold`, `cond`, `gen`, `inlines`, `parts`, `expr`, `decl`, `lathec`, `rt_math`, `rt_bbc`, `rt_frame`), its source from drive 0, its object and interface to drive 1, the interfaces of its imports found there: `*LATHE -c6502 -dROMFORM=0 -dADFS=1 -dBOARD=3 -dPORTS=2 -dBBCFS=2 -dTEXTS_IN_MODULE=0 -dMODULE_SLOT=4 -dSMALL=0 0/err.lth 1`.
3. Link: `*LLINK @LINKARG` writes `:1.LATHEC`, its six bank files `:1.BIN.LATHE1` ... `:1.BIN.LATHE33` and then the map `:1.map.LATHEC`.
4. Give the image its addresses, on the drive its banks are on: `*DIR :1`, `*LOAD LATHEC 1F00`, `*SAVE LATHEC 1F00 +LENGTH 1F00` (the length from `*INFO LATHEC`).
5. Run the new compiler: `*RUN LATHEC -c6502 -dROMFORM=0 -dADFS=1 -dBOARD=3 -dPORTS=2 -dBBCFS=2 -dTEXTS_IN_MODULE=0 -dMODULE_SLOT=4 -dSMALL=0 0/err.lth 1` (its start-up loads its banks from `bin` of the current directory into the module's RAM, over the tools'). It writes `:1.lo.err` and `:1.li.err` over the ones `*LATHE` made, the same bytes. The developer's form marks the module's slot as no ROM in the MOS's table when it loads its banks ([`bbc.md`](bbc.md), "ADFS", "Faults found"), so `*LATHE` and `*LLINK` need `*RUN :1.LOADMOD :1.MODULE` again after it.

What the discs hold at the end, measured by the emulator (where the test stands in for step 1 with the module's RAM filled at power on, and runs every other step as written): disc A (drive 0) 27 files, 584,430 bytes, 2,313 of its 2,560 sectors, 247 free (62 KB) (with the message file `LATHERR` of 2026-11-17, as the 128 KB run had it then, 28 files and 2,391 sectors: the file was 37 sectors, and the sources and the environment have grown since; the texts are in the module now); disc B (drive 1) 58 files, 626,379 bytes, 2,500 sectors, 60 free (15 KB); at most 25 entries in a directory. So the 64 KB a new file is given at OPENOUT are there for every file the loop creates (the map last, on drive 1, with 551 sectors free when it is created); after the loop drive 1 has less than 64 KB free, so a second rebuild should `*DELETE` the old map (or the objects) before it starts: a file that is there is written over in its own space, but a new file needs 256 free sectors in one run. One file is written at a time and two are open at most.

For a program of your own, build it with `bbc.env` (or `bbc-bank.env`) with `define BBCFS 2` and `define ADFS 1`: it loads at `$1F00`, its sources go in `lth`, and the tools' command lines are as on the host.

#### Loading new tools: MODLOAD

On the developer's machine (the module's RAM form, sixteen banks), new tools linked in their ROM forms on the BBC become the live `*LATHE` and `*LLINK` without the host ([`bbc.md`](bbc.md), "The developer's cycle"):

    *RUN MODLOAD HOME lathe.env lathe.map LATHE llink.env llink.map LLINK     the whole module
    *RUN MODLOAD lathec-bbc.env 1/LATHEC.map 1/LATHEC                       one tool, the rest kept

each tool's ROM environment, its map and its resident image, the bank files beside the image. `HOME` is the module's home bank, made once on the host: `bbcrom.py --banks 16 --whole --home HOME -o WHOLE ...` with the tools as in "The tool chain on the BBC". The first form fills an empty RAM form (from a disc the host makes once: MODLOAD, HOME and both tools' link outputs); the second writes one tool, just linked, into its own banks of the module there, and refuses a module it does not know or a tool whose start or memory moved (a new HOME is needed then).

**A tool's pair of discs** ([`bbc.md`](bbc.md), "The discs: a pair for each tool", has the counts): drive 0, the tool's sources as `lth.NAME`, its ROM environment as `env.NAME` (`lathec-bbc.env` or `linker-bbc.env` through `bbcrom.rom_env`, with `BBCFS 2` and `ADFS 1`), the link's command file `LINKARG` (the environment, the main module, `1/IMAGE`, `1/IMAGE.map`, then each object as `1/NAME.lo`) and MODLOAD; drive 1 blank. A turn: `*LATHE OPTIONS 0/NAME.lth 1` for each module in build.py's order, `*LLINK @LINKARG`, `*RUN MODLOAD ENV 1/IMAGE.map 1/IMAGE`; the tool is live at once. `../tests/test_bbc_cycle.py` (`LATHE_BBC_CYCLE=1`) runs two turns of each pair on the emulator. Build MODLOAD with `lathe/src/modload-bbc.env` (with ADFS: `test_bbc_adfs.adfs_env` of it). It checks every file against the others before it writes, and says `modload: ...` and `Exit 2` if they do not belong together. `--bbc-module-dump FILE` writes the module's banks at the end of the run.

## The VIA timer

Both boards have a 6522 VIA. Its base is `$6000` on Michael and `$F000` on Wendy 2.

| Register | Address | Use |
|---|---|---|
| T1CL | base + `$4` | Timer 1 counter, low byte. Reading it acknowledges the interrupt. |
| T1CH | base + `$5` | Timer 1 counter, high byte. Writing it starts the timer. |
| ACR | base + `$B` | Auxiliary control. `$40`: timer 1 runs free, reloading from its latch. |
| IFR | base + `$D` | Interrupt flags. Writing `$40` also acknowledges timer 1. |
| IER | base + `$E` | Interrupt enable. `$C0` enables timer 1; `$40` disables it. |

The steps:

1. `SEI`, and put the handler in the vector (`$3F00` or `$FFFE`).
2. Write `$40` to ACR.
3. Write the latch: T1CL first, then T1CH. A latch of `$07CE` gives a period of 2000 cycles.
4. Write `$C0` to IER.
5. `CLI`.

The handler reads T1CL to acknowledge the interrupt, then ends with `RTI`.

## Board modules

Lathe modules in `../rt/` that run a program on either board with no edit to its source. The environment file names the board, `define BOARD 1` in `michael.env` and `define BOARD 2` in `wendy2.env`. `board.lth` turns that number into the facts in this document, and the other modules read them from it. `build.py --env michael` or `--env wendy2` picks the board. These modules do not compile for `host.env`, which has no `BOARD`.

| Module | What it gives |
|---|---|
| `board.lth` | Constants: `MICHAEL`, `WENDY2`, `VIA` (the base), `CLOCK_KHZ`, `LCD_ROWS`, `LCD_COLS`, `LCD_4BIT`, and `IRQ_JMP` with `IRQ_VECTOR` (`$3F00` takes `JMP handler`; `$FFFE` takes the handler's address). `set_irq(handler)` makes the IRQ vector lead to `handler`, the address of an interrupt function (`@name`), through variables `at` those addresses; call it with interrupts disabled. `delay(units)`, an `asm` function, waits at least `units` times 100 microseconds. |
| `via.lth` | The VIA's sixteen registers as variables at fixed addresses (`via.portb`, `via.porta`, `via.ddrb`, `via.ddra`, `via.t1cl` … `via.ier`, `via.porta_nh`), and the bits `ACR_T1_MASK`, `ACR_T1_FREE_RUN`, `IRQ_T1`, `IER_SET`. |
| `lcd.lth` | `init()`, `clear()`, `home()`, `goto(row, col)`, `put(ch)`, `print(s)`, `print_hex(b)`, `print_dec(w)`, and `command(c)` with the `CMD_` constants. |
| `timer.lth` | `start(period)` sets up an interrupt from timer 1 every `period` CPU cycles (latch `period - 2`), with the module's own handler, sets the count to 0, and runs `CLI`. `start_with(period, @handler)` does the same with a program's own interrupt function, which must call `acknowledge()`, an exported inline function that acknowledges the interrupt and counts it. `stop()` disables timer 1's interrupt. `ticks()` gives the count, read inside `critical`. |

How the modules treat the hardware:

- **The LCD** is started by instruction, as the data sheet says: 15 ms, then three function sets with 4.1 ms and 100 µs between them, then the switch to 4 bits on Wendy 2. `board.delay` gives those waits. After that, every transfer waits for the busy flag, on both boards, as `../../firmware/lib/lcd/` does. The emulator never sets the busy flag, so the waits end at once there. (On Wendy 2 nothing drives the data pins during a read, and they read 0.)
- **Port B on Wendy 2.** A pulse on E reads port B, changes bit 5 and writes the byte back, inside `critical`. No shadow copy is kept. For an output pin, the 6522 reads back its output register, so the bank bits come back exactly as they were last written, whoever wrote them.
- **Port A on Michael** is set up as `../../firmware/boards/michael/michael_ports.inc` does it: first `$18` (SOEB and SOLB high, so the keyboard's shift register stays off port B), then direction `$FE`. The Michael section above gives `$EE`, which leaves SOEB (PA4) as an input. The firmware drives it.
- **The timer's handler** is an `interrupt` function in Lathe, `tick()`: its entry code saves A, X and Y, it acknowledges the interrupt by writing `IRQ_T1` to IFR and counts, and its exit code restores the registers and ends with `RTI`. `start()` installs it with `board.set_irq(@tick)`. A program's own handler gets storage of its own for whatever it calls (`../tests/cases/e2e-michael/irq_shared.lth`).

The cases in `../tests/cases/e2e-michael/` and `e2e-wendy2/` use these modules. Each Wendy 2 case is a link to the Michael case of the same name. Only the expected text differs.
