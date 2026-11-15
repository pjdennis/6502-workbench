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
- **Files.** OSFIND with the name ended by CR. A missing file is 0, as the MOS gives it; an error the filing system raises instead (`Bad name`, `Too many open files`) is caught for the call through BRKV and is 0 too, so that `open` keeps host's contract. At the end of a file `read` gives the carry set, and keeps giving it without calling OSBGET again, which would raise the error `EOF`. Names are passed as they are: the emulator takes any name without `/` or `..`; a real DFS takes seven characters and uses `.` for its directory.
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
