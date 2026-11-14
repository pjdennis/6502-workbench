# Running on the boards

A Lathe program can run on three machines of the emulator (`../../emulator/README.md`): the default machine, Michael and Wendy 2. Each has an environment file in `../env/`. This document gives the recipe for each: how the emulator is run, the memory map, what the file must hold, how output is read, and how a timer interrupt is set up.

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
- **The end.** The run ends at `STP` or at the cycle cap. There are no host services.
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
