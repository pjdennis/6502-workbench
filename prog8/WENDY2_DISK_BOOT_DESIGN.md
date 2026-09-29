# wendy2 disk boot: alternate monitor ROM + file-I/O program loading

How to get from "serial-upload one program" to "a boot monitor that loads
and runs programs from (simulated) mass storage, with autoexec." This is
the design doc for that subsystem; it resolves and consumes the `$F800+`
OS-call file I/O from
[`WENDY2_BANKING_TARGET_PLAN.md`](./WENDY2_BANKING_TARGET_PLAN.md) S2.6 (M5).

> **Status: D1-D2 + D4 built and green, plus banked-code loading (T5/T6) and packaged multi-bank images (D5).**
> The `$F800+` OS-call port chip + `--disk` (D1), the monitor ROM with autoexec
> load+run (D2), return-to-monitor + multi-command autoexec (D4), and loading
> code into multiple banks + executing across them (T5/T6) are implemented and
> tested (`make -C toolchain/prog8 wendy2-test`: 12 e2e goldens). Implementation:
> `emulator/chips/syscall_ports.{c,h}`, `wendy2c_monitor.s`,
> `toolchain/prog8/upstream/libraries/wendy2/os.p8`, demos `d1_*`/`d2_*`/`d4_*`/`t5_*`/`t6_*`/`d5_*` + `wendy2_pack.py`.
> Remaining (future work): D3 (interactive serial commands -- deferred),
> D6 (real SPI-flash image backing).

Companion:
[`upstream/libraries/wendy2/README.md`](./upstream/libraries/wendy2/README.md)
(the working banked target).

---

## 1. Vision & scope

**Ultimate (hardware):** prog8 programs run on wendy2 with SPI-based mass
storage; a boot monitor loads/runs programs from SPI, with an autoexec.

**Now (emulator):**
1. **Simulate the storage** -- a "disk" the emulator exposes through the
   file-I/O OS calls.
2. **Alternate boot ROM** (a monitor) that loads & runs programs from that
   storage, driven by an **autoexec** file and/or **serial commands**.
3. **Load programs over the file-I/O OS calls** (the `$F800+` ABI), not the
   serial-upload framing.

The existing serial-upload boot ROM (`upload_and_run_eeprom_wendy2c.s`)
stays as-is for the current demos; the monitor is a *second* ROM selected
with the emulator's `--rom` flag.

## 2. Layered architecture

```
  prog8 program (.p8)  --prog8c(wendy2)-->  prog.bin (RAW @ $4000)
        |                                        |
        |                                  stored as a file on
        |                                        v
        |                              [ simulated SPI "disk" ]   (host dir)
        |                                        ^
        v                                        | file-I/O OS calls ($F800+)
  MONITOR ROM ($8000-$FFFF) --reads--> loads prog.bin into $4000 --> JSR/JMP
        ^                                                                |
        |  serial commands (--serial-input)  +  autoexec file           |
        +------------------ warm-start on program exit -----------------+
```

Four new pieces: a **syscall-port chip** (emulator), a **disk backing**
(emulator), the **monitor ROM**, and **OS-call wrappers** in the syslib.

## 3. Simulated SPI storage (emulator)

For now, back the file-I/O OS calls onto a **host directory** ("the disk"):
one host file per stored file, opened by name. This reuses the existing
`file_io.c` (`file_open`/`file_open_for_write`/`file_read`/`file_write`/
`file_close`/`dir_open`) verbatim -- the same backend the nmos machine uses.

* New flag: `--disk DIR` (alias `--spi-dir`). Filenames in OS `open` resolve
  relative to `DIR`. Default: the cwd, or a `disk/` next to the ROM.
* A real SPI-flash filesystem (a flat image + a tiny directory format) can
  replace the host-dir backing later **behind the same OS-call ABI** -- the
  guest code and monitor don't change. That's the whole point of routing
  through the ABI now.

## 4. The file-I/O OS-call ABI (`$F800-$F80F` port block)

This is M5, with the two open questions from the banking plan resolved:

* **Backing:** the simulated disk (S3), not stdin/stdout.
* **No CPU-register coupling.** The bus-chip `read`/`write` only see
  `addr`+`data`, not A/X. So arguments go through **ports**, and the chip
  pulls strings/data out of guest RAM with `bus_read` (it has the `bus`).
  A **current-handle** port removes per-call handle args.

Proposed port map (a `syscall_ports` chip that claims `$F800-$F80F`,
registered *before* RAM so it intercepts; everything else falls through):

| port | R/W | meaning |
|------|-----|---------|
| `$F800` | W | arg pointer low  (e.g. filename address in guest RAM) |
| `$F801` | W | arg pointer high |
| `$F802` | R | open-for-read  -> handle in A (0 = fail); chip reads the name from RAM at the arg pointer |
| `$F803` | R | open-for-write -> handle |
| `$F804` | W | select current handle |
| `$F805` | R | read byte from current handle (advances) |
| `$F806` | R | EOF of current handle (bit 7 set = at end) |
| `$F807` | W | write byte to current handle |
| `$F808` | W | close current handle |
| `$F809` | R | opendir(arg pointer) -> handle (directory listing stream) |
| `$F80A` | R | argc (serial/monitor-supplied args) |
| `$F80B` | W | select arg index; `$F80C/$F80D` R = that arg's addr lo/hi |
| `$F80E` | W | warm-start / "return to monitor" (program exit) |
| `$F80F` | W | power-off / halt the emulator (code = data) |

`$F800-$F80F` is carved out of the fixed `$F800-$FFFF` RAM window; the rest
($F810-$FFF9 RAM + vectors $FFFA-$FFFF) is untouched. Because the chip is
address-gated and additive, it cannot regress any existing emulator test.

**syslib wrappers** (`libraries/wendy2/os.p8`, callable from any bank since
the ports are fixed): `os.open(name)->handle`, `os.openout(name)->handle`,
`os.read(handle)->ubyte` + `os.eof(handle)->bool`, `os.write(handle,b)`,
`os.close(handle)`, `os.opendir()`, `os.argc()/os.argv(i)`,
`os.exit_to_monitor()`, `os.poweroff(code)`.

## 5. The monitor ROM (`wendy2c_monitor.s`)

A small ROM at `$8000-$FFFF` (the reset/config-`$00` view). Flow:

1. **Reset/init:** set up VIA + HD44780 (reuse `initialize_machine_wendy2c.inc`
   + `display_routines_4bit.inc`), switch to default bank `$01`, install the
   IRQ vector in fixed RAM, print a banner.
2. **Autoexec (S6).**
3. **Command loop:** read a line from serial (the `--serial-input` queue via
   the VIA SR, same path the upload ROM uses) and dispatch.

**Commands** (text lines, case-insensitive):

| command | action |
|---------|--------|
| `run NAME`  | load `NAME` from disk to `$4000`, then execute it |
| `load NAME` | load only (no run) |
| `dir`       | list disk files (via `opendir`) to the LCD/serial |
| `poke A V` / `peek A` | tiny memory ops (debugging) |
| `bank N`    | select upper bank N (debugging) |

**Load mechanism (the core "load over file I/O"):**

```
  h = os.open(NAME)                ; via $F800/$F801 + $F802
  if h==0: report "not found"
  os.select(h)                     ; $F804
  ptr = $4000
  while not os.eof(h):             ; $F806
      @(ptr) = os.read(h)          ; $F805
      ptr++
  os.close(h)                      ; $F808
  ; run: switch to bank $01, JMP $4000
```

Program format: either a **flat** binary (load `$4000`, entry `$4000` --
exactly what `prog8c -target wendy2` emits), or a **multi-segment `.w2x`
image** (BUILT, D5). The monitor auto-detects the `"W2X"` magic prefix:

    "W2X"  nseg(1)  then nseg x [ bank(1) addr_lo addr_hi len_lo len_hi data... ]

bank 0 = the fixed lower 32K (main @ `$4000`); banks 1-7 = an upper RAM
bank (code/data @ a `$8000-$EFFF` window addr). The monitor streams each
segment into its target bank, then launches `$4000`. `upstream/wendy2_pack.py`
builds the image (`wendy2_pack.py -o app.w2x main.bin ov.bin@1@A000 ...`).
This is the "loader distributes a packaged program's code across banks"
model (vs. the binary self-installing it, T5, or runtime overlay loading,
T6). Per-segment streaming runs from a lower-RAM stub because the monitor
runs from ROM and can't hold a RAM bank in the window while executing.

**Return-to-monitor convention:** programs end either by
`os.exit_to_monitor()` (`$F80E` -> chip forces a warm-start jump back into
the monitor; enables an interactive loop and multi-command autoexec) or by
`STP`/`$F80F` to halt (what the current demos/tests do). The monitor's
warm-start re-enters at the command loop without re-running init.

## 6. Autoexec

At boot, after init, the monitor tries `os.open("autoexec")`. If present, it
reads the file line by line and runs each line as a command before (or
instead of) the serial loop. Example `autoexec`:

```
dir
run hello
```

This is the **smallest end-to-end slice** (no serial parsing needed): it
exercises the alt ROM + file I/O + load + run in one shot, and is trivially
goldenable (boot monitor with a disk dir containing `autoexec` + `hello.bin`
-> assert the LCD shows hello's output).

## 7. Emulator changes (small, isolated)

1. `chips/syscall_ports.{c,h}` -- the `$F800-$F80F` chip (S4), backed by
   `file_io.c`, holding `current_handle` + `arg_ptr` state; uses `bus_read`
   to fetch names from guest RAM.
2. `emu_wendy2c.c` -- register the chip **before** `ram_628128`; add the
   `--disk DIR` option (call `files_init`/chdir or pass DIR into the chip);
   wire `$F80F`/`$F80E` to the existing exit/longjmp path.
3. CLI: `--disk DIR`. Everything else unchanged.

No change to the bus, RAM, VIA, PLD, or any existing chip -> existing
`make test` stays green by construction.

## 8. Building & storing programs

```
  prog8c -target wendy2.properties -out OUT hello.p8    # -> OUT/hello.bin @ $4000
  cp OUT/hello.bin   $DISK/hello                         # "store on SPI"
  printf 'run hello\n' > $DISK/autoexec                  # optional autoexec
  emulator --machine wendy2c --rom wendy2c_monitor.bin --disk $DISK
```

The monitor ROM is built once with vasm (like the upload ROM).

## 9. Run/test harness

* `upstream/wendy2_disk_run.sh PROG.p8 [extra disk files...]`: compile, drop
  `PROG.bin` + an `autoexec` (`run PROG`) into a temp disk dir, boot the
  monitor ROM with `--disk`, capture the LCD frame.
* `tests/test_wendy2_disk.py`: golden test -- autoexec runs a known program;
  assert its LCD output. Skips if toolchain/emulator missing. Wire into
  `make wendy2-test`.

## 9b. Loading code into upper banks (the two models) -- BUILT

How does banked *code* get into the upper banks? Upstream Prog8 shows two
patterns, and wendy2 supports both (demos T5 and T6). In all cases the
resident program in the fixed lower 32K is the **conductor**: banked code is
an *overlay* it `bank_call`s into (the overlay's own code is switched out of
the window the moment it would switch banks, so cross-bank control flow is
orchestrated from the fixed region, never overlay-to-overlay directly).

The two ways to get the bytes into a bank:

1. **Self-installing binary** (T5 `t5_multibank_code.p8`). The compiled
   program carries the routines as data (byte arrays) and copies them into
   banks at startup with `banking.bank_store(n, win, &blob, len)`. This is
   the analog of a program copying overlays into HIRAM with byte stores --
   on the C128, `INDSTA` ($FF77) stores into another bank; our `bank_poke` /
   `bank_store` are the same idea. Self-contained: no storage needed, runs
   under the plain upload boot ROM. Good for small, fixed overlays baked into
   the build.

2. **Storage-driven / environment loads** (T6 `t6_overlays.p8`). The program
   streams overlay *files* from the disk straight into banks
   (`os.openfile` + `set_upper_bank` + read loop = "LOAD-into-bank"). This is
   the analog of how a real banked program gets code on upstream targets: the
   **kernal/loader** places a file into a chosen bank -- C128 `SETBNK`
   ($FF68) selects the bank, then `LOAD` streams the file in; cx16 likewise
   `LOAD`s a file into a HIRAM bank. The banked code lives outside the main
   binary, supplied by the environment, and can be swapped/updated without
   rebuilding the program. This is the model to grow toward for real overlay
   management (and the natural home for a future `loadbank NAME N` monitor
   command).

Both demos install three routines into banks 1/2/3 and `bank_call` across
them; each routine also bumps a shared counter in fixed lower RAM (banked
code reaching back into the always-mapped lower 32K), proving distinct code
really executes in each bank (T5 -> `123 n=3`, T6 -> `abc n=3`).

Far-call mechanism: `banking.bank_call(n, win)` saves the current bank,
selects bank n, `jsr`s the overlay via a zero-page vector, restores the bank
on return -- the wendy2 analog of cx16 `callfar` / C128 `JSRFAR` ($FF6E),
with the trampoline resident in the fixed lower 32K so the return survives
the switch.

## 10. Milestones

* **D1 -- syscall-port chip + `--disk`** (emulator). Unit-check: a tiny
  hand-asm program that `os.open`/`read`s a file and writes a byte to the
  LCD. Proves the ABI + disk backing.
* **D2 -- monitor ROM, autoexec-only.** `autoexec` containing `run NAME`
  loads+runs a prog8 program from disk. End-to-end golden. *(smallest slice
  that realizes the whole vision)*
* **D3 -- serial command loop.** `run`/`load`/`dir` over `--serial-input`.
* **D4 -- warm-start / exit-to-monitor** so multiple commands / an
  interactive session work; `os.exit_to_monitor()`.
* **D5 `[done]` -- richer program format** (`.w2x` multi-segment image:
  per-segment bank + addr + len) so the loader places code/data into upper
  banks. `wendy2_pack.py` builds it; the monitor auto-detects the `W2X`
  magic. Demo `d5_banked_app` -> `123 n=3`.
* **D6 (later, hardware) -- real SPI flash backing** behind the same ABI: a
  flat image + a tiny FS, and a real SPI driver in the monitor; the guest
  ABI and prog8 programs are unchanged.

## 11. Open questions

* **Disk model fidelity.** Host-dir-per-file now vs. a flash image + FS
  later. The ABI hides it; pick the image format when targeting real SPI.
* **argc/argv source.** For `run NAME arg1 arg2`, the monitor must publish
  args to the loaded program (write them into RAM + expose via `$F80A-$F80D`),
  mirroring the nmos argv stubs.
* **Banked programs.** The raw-`$4000` format keeps programs in the fixed
  lower 32K. Programs that put code/data in the upper banks need D5's header
  (which bank, which window address) and the monitor to bank-load them.
* **Memory overlap.** The monitor loads to `$4000`; its own scratch/stack
  must stay clear of `$4000-$7FFF`. Keep monitor RAM in `$0200-$03FF` +
  `$F810+` fixed high RAM.
* **Self-hosting tie-in.** Once D1-D2 land, the on-target prog8 toolchain
  (compiler reading source, writing `.bin`) can read/write the disk through
  the same OS calls -- the long-term reason M5 exists.
</content>
