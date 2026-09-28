# Timing accuracy: the CPU and the VIA

Where the emulator's cycle timing differs from the real W65C02S and W65C22, what that
breaks, and how to fix each difference. References are to the WDC W65C22 data sheet
(figures 2-3, 2-4 and 2-6) and the W65C02S data sheet.

## What is accurate

- **VIA timers T1 and T2** (`chips/via_6522.c`), per data sheet figures 2-3 and 2-4. A
  counter written through T1CH or T2CH reads N on the next cycle, then counts down. It
  times out as it rolls over from 0 to $FFFF, and the interrupt flag shows on that cycle,
  N+2 cycles after the write. The data sheet's IRQB falls N+1.5 cycles after the
  write, within that cycle.
  - T1 then reloads from its latch, so free-run interrupts come every N+2 cycles.
  - T1 one-shot mode keeps counting from the latch but sets its flag only once per
    write.
  - T2 keeps counting down from $FFFF and sets its flag once per write.
  - `tests/test_chip_via.c` pins each of these behaviours.
- **Timer intervals measured by a program.**
  `firmware/programs/michael/michael_timer2_test2.s` reads T2 in its
  interrupt handler and re-arms it to keep exact 500 Hz ticks.
  - `make timer2-cycles` runs it on the CPU and VIA chips through
    `tests/via_t2_runner.c`. It checks that the ticks are exactly `DELAY` cycles apart,
    while the handler's own delay varies from 9 to 60 cycles.
  - The handler's `RESTART_OFFSET` was tuned on the board, so this test checks the
    emulator against real hardware.

Within one cycle the VIA ticks before the CPU: in both machines, `via_chip` is added to
the bus ahead of `cpu_chip`. So a CPU access sees the VIA's state for that cycle. The
VIA unit tests model the same thing by writing or reading between `tick()` calls. Any
change below must keep this order, or the timers slip by a cycle.

## 1. The CPU does a whole instruction on its first cycle

`chips/cpu_65c02.c` calls `step6502()` on an instruction's first cycle. That call
fetches the opcode, does every bus access, and updates the registers. The CPU then
idles for the remaining `cycles_owed` cycles. On the real 65C02, each access happens
on its own cycle, and the data access is usually the last one.

**Effect.** The emulator reads and writes devices a few cycles early: 3 cycles early
for `lda abs` or `sta abs`, and 4 or 5 for `lda (zp),y`.

- Intervals between two accesses of the same shape are still exact. That is why
  `michael_timer2_test2.s`'s read of T2CL and write of T2CH, both 4-cycle absolute
  instructions, come out right.
- Intervals between accesses of different shapes are off by the difference in their
  positions. For example, a timer read with `lda (ptr),y` against a start written with
  `sta abs`.
- Code that counts cycles against a device is affected the same way: bit-banged
  serial, LCD strobes with tight setup times, and anything that polls a timer.

**Fix.** The cheaper fix delays `step6502()` to the cycle of the instruction's data
access:
1. Add a table, per opcode and CPU variant, of the cycle (1-based) on which the
   instruction reads or writes its operand. For read-modify-write instructions, use
   the write cycle.
2. On an instruction's first cycle, peek the opcode at `pc` without side effects. That
   is safe because opcodes come from RAM or ROM.
3. Owe `access_cycle - 1` cycles, then run `step6502()`, then owe the rest.

Read-modify-write instructions would still read and write on the same cycle, which
matters only for device registers such as `inc PORTB`. Interrupt sampling (section 2)
has to move with the instruction's end, not with the `step6502()` call.

The full fix is a per-cycle 65C02 core, with one bus access per cycle and dummy reads
included. With it, `tests/harte_runner.c` could turn on its cycle-log check
(`cycle_check`). That check currently fails by design, because a whole-instruction
core can't produce the per-cycle bus log.

**Tests.** Add a CPU and VIA test in the style of `via_t2_runner` that reads T1 or T2
with instructions of different shapes (`lda abs`, `lda abs,x`, `lda (zp),y`) a known
number of cycles after starting the timer. Assert the values the W65C02S cycle tables
predict.

## 2. Interrupts are taken instantly and cost no cycles

`cpu_65c02_tick` calls `irq6502()` (or `nmi6502()`) on any cycle where the CPU is
between instructions and the line is up. It then runs the handler's first instruction
in the same cycle. `irq6502()` pushes PC and P and loads the vector, but adds nothing
to `clockticks6502`, so `cycles_owed` never sees the 7 cycles of interrupt entry.

On the W65C02S, the CPU polls the interrupt lines during an instruction's last cycle.
An interrupt raised later than that waits for one more instruction. Entry then takes
7 cycles before the vector's first opcode fetch.

**Effect.** Handlers start at least 7 cycles early, often more.

- In `timer2-cycles`, the handler reads T2CL just 9 cycles after the time-out, which is
  exactly its `pha`/`phx`/`phy`. On the board it would be at least 7 + 9 = 16 cycles,
  plus whatever remained of the instruction that was running.
- Handlers that compensate by measuring, as `michael_timer2_test2.s` does, aren't
  affected.
- Handlers whose timing is counted from the interrupt are affected. That includes
  the serial loader's start-bit handler in `firmware/lib/serial/upload_and_run.inc`,
  which counts the cycles "to get here" before it starts the shift.
- Interrupts per second (CPU load) are also overstated.

**Fix.**
1. In `cpu_65c02_tick`, when dispatching an IRQ or NMI, charge the entry: owe 6 more
   cycles and return without calling `step6502()` in that cycle.
2. Sample the line on the instruction's last cycle, when `cycles_owed == 1`, rather
   than at the next boundary. Latch the result so the interrupt is taken after this
   instruction, or after the next one if the line rose too late.
3. Charge a wake-up from `WAI` the same entry cost.

**Tests.** Extend `tests/test_chip_cpu_65c02.c`, or use a small runner, to assert the
cycle of the handler's first access relative to the cycle the VIA raised IRQ.
Check that `timer2-cycles` still passes: its intervals must not change.

## 3. The shift register under T2 shifts at the wrong rate

In SR mode 001 (shift in under T2 control, `VIA_ACR_SR_IN_T2`), the model shifts one
bit on every T2 underflow and reloads T2 from its low latch straight from 0. That is
one bit every N+1 cycles.

On the real chip (data sheet 2.12.2, figure 2-6), each time-out of T2's low byte toggles
CB1, and data shifts in on the cycle after each rising edge of CB1. A time-out takes
N+2 cycles, as for the timers, so a bit takes 2(N+2) cycles. The loader counts on this.
In `firmware/lib/serial/upload_and_run.inc`, `SUBSEQUENT_INTERVAL = HALF_BIT_INTERVAL - 2`
makes each CB1 half-period half a bit. For the wendy2c, at 9.72 MHz and 115200 bps,
that is N = 40, or 84 cycles per bit (the ideal is 84.375). The emulator shifts every
41 cycles.

**Effect.** In the emulator the loader samples about twice per bit-time. Two
workarounds hide this:
- `chips/serial_usb.c` (`--serial-input`) paces on `sr_shift_total`: it puts the next
  bit on CB2 after each shift, whatever the cycle count.
- `wendy2c_emu_upload.py`, which drives `--serial-link` in real time, sends at 230400
  baud by default instead of the board's 115200. At that rate a bit lasts 42.2
  cycles, close enough to one shift per bit.

Neither exercises the bit timing the loader was tuned for on hardware, including the
interval from the start-bit interrupt to the first sample.

**Fix.**
1. Model CB1 as the T2 time-out divided by 2. In SR-under-T2 modes, T2's low byte
   counts N, …, 0, then one more cycle, then reloads N.
2. At each time-out, toggle CB1. On each rising edge, shift CB2 in on the following
   cycle. Mode 001 stops after 8 bits and sets IFR.SR. Reading or writing SR restarts
   the count, as now.
3. Pace the serial drivers on wire time rather than on shifts. Hold each bit on CB2
   for the real bit time from the start edge, so that a loader whose interval is wrong
   samples the wrong bits, as it would on the board. Change
   `wendy2c_emu_upload.py`'s default back to 115200 and drop its explanation of the
   doubled rate.

**Tests.**
- Update the SR tests in `tests/test_chip_via.c`: 2(N+2) cycles per bit, with the first
  sample at the first rising edge of CB1.
- Run the wendy2c goldens (`--serial-input`) and `wendy2c-serial-link` (real time,
  now at 115200), and the Michael loader tests on `michael-editor`.

## 4. VIA features that aren't modelled

None of these affect timing today, but a program that relies on one behaves
differently:
- **ORB access and the CB flags.** Reading or writing ORB doesn't clear IFR.CB1 or
  IFR.CB2. CB2 is modelled only as a negative-edge input.
- **CA1, CB1 and CA2.** No CA1 or CB1 edge interrupts. `michael-editor` adds CA2 edges
  and the IFR.CA2 clear on an ORA access.
- **Handshake and pulse output modes** on CA2 and CB2.
- **T2 pulse counting** on PB6 (ACR5 = 1). T2 always counts PHI2 cycles.
- **Other SR modes.** Shift out under T2, PHI2 or CB1, and shift in under PHI2 or an
  external CB1, aren't modelled.
- **The IRQ half cycle.** IRQB falls partway through the time-out cycle (N+1.5 cycles
  after the write). The model raises it for the whole cycle, which is right at the
  CPU's one-cycle resolution.

**Fix.** Each is local to `via_6522.c`. Add the behaviour with a unit test in
`tests/test_chip_via.c` when a program first needs it.

## Checking changes against the boards

- `make timer2-cycles`: exact T2 tick intervals for a handler tuned on the board.
- `make harte` (opt-in, needs `tests/harte/fetch.sh`): instruction results. Once
  section 1's full fix exists, turn on the cycle-log check.
- On `michael-editor`, the Michael machine (`--machine michael`) runs
  `michael_timer2_test2.s` through the real ROM's serial loader. Over 200 s of emulated
  time (400,000,000 cycles), its LCD clock and tick count advance by exactly 200.00 s
  and 100,000 ticks.
