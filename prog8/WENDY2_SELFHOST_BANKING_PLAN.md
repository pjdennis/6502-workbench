# Plan: self-host p1.p8 on wendy2 using banking

How to run the Prog8 self-hosting compiler (`p1.p8`) on the **wendy2c**
machine, using the upper-window memory banking to hold what doesn't fit in
the 32 KB fixed region. Assumes a companion effort has already made `p1.p8`
**fully upstream-syntax** (so it compiles with upstream `prog8c` for the
custom `wendy2` target).

Planning doc only -- no code yet. Builds on the shipped wendy2 banking +
disk-boot infrastructure
([`WENDY2_BANKING_TARGET_PLAN.md`](./WENDY2_BANKING_TARGET_PLAN.md),
[`WENDY2_DISK_BOOT_DESIGN.md`](./WENDY2_DISK_BOOT_DESIGN.md)).

---

## 1. Goal & context

Run `p1.p8` (lex -> parse -> codegen) **on wendy2c** and have it reproduce
its own host-compiled `.s` byte-for-byte (the self-host fixpoint), reading
source and writing output from the simulated SPI disk. The existing
self-host already works on the emulator's *nmos* machine (60 KB flat RAM,
two passes exchanging the AST through a file -- see `PLAN.md` "Goal
REACHED"). wendy2c's contiguous RAM is only **32 KB** ($0000-$7FFF), so the
compiler doesn't fit flat there; banking supplies the rest.

## 2. The sizing reality (why, and what overflows)

Measured with upstream `prog8c` (the wendy2 target's compiler) on the
current two-pass split:

| pass | code | footprint top (memtop) |
|------|------|------------------------|
| `p1_pass1_sh` | ~17 KB ($0200-~$44DB) | $8300 |
| `p1_pass2_sh` | ~26 KB ($0200-~$6800) | $9f00 |

The decisive facts:

* **Each pass's *code* fits below `$8000`** (pass2 code tops out ~`$6800`),
  i.e. inside wendy2c's fixed lower 32 KB.
* What spills past `$8000` is **data** -- prog8 vars/BSS + the baked arena
  *slabs* (the port already moves the >256-element arenas to raw-RAM
  peek/poke slabs). On nmos these just live in flat RAM up to memtop
  `$F000`; on wendy2c that region is the banked window.

So the overflow is data, not code -- which is the easy case for banking.

## 3. Key insight: one bank held mapped == flat high RAM

wendy2c memory under a RAM-bank config (e.g. logical bank 0 = PORTB `$01`):

```
  $0000-$7FFF  fixed lower RAM   (code + low vars + ZP + stack)
  $8000-$EFFF  the mapped bank   (28 KB)  <- prog8 high vars/BSS/slabs
  $F000-$F7FF  VIA
  $F800-$FFFF  fixed high RAM + OS-call ports ($F800-$F80F) + vectors
```

If the pass runs with **one RAM bank held mapped** in `$8000-$EFFF` and
never switches it, then `$0200-$EFFF` behaves exactly like the nmos flat
layout (`load $0200`, `memtop $F000`) -- except the top 28 KB is a bank.
Because the pass's **code is entirely below `$8000`** (S2), and its data
fills upward into the mapped bank, **no per-access bank switching, no code
overlays, and no arena partitioning are needed**. The compiler is the same
two passes; banking just supplies the high 28 KB of each pass's RAM.

The monitor's launch stub already maps a RAM bank (PORTB `$01`) before
jumping to a loaded program, so the bank is mapped for free.

## 4. Architecture (two-pass retarget)

```
  source.p8 (on SPI disk)
     |  monitor autoexec: run pass1
     v
  pass1  (code $0200-~$6800 fixed; vars/AST slabs in the mapped bank)
     |  writes the AST dump to the SPI disk (OS-call file I/O)
     v
  ast.bin (on SPI disk)
     |  monitor autoexec: run pass2   (pass1 returned to monitor)
     v
  pass2  (code fixed; AST + symbols + codegen arenas in the mapped bank)
     |  writes source.s to the SPI disk
     v
  source.s
```

* **Each pass** = one upstream-compiled wendy2 program, `load $0200`,
  `memtop $F000`. Loaded from disk by the monitor; runs with bank `$01`
  mapped (high RAM). Code < `$8000`; data in `$8000-$EFFF`.
* **I/O** = the `$F800+` OS calls (`os.p8`): open/read/write/close on the
  SPI disk. The compiler's I/O shim is retargeted from the nmos `$F006+`
  stubs to these (the one real source change to the passes -- see S5).
* **AST hand-off** = a disk file (same as the nmos pipeline, just on the
  SPI disk). Optionally in a bank (S6).
* **Sequencing** = the monitor's multi-line `autoexec` (`pass1` then
  `pass2`), using return-to-monitor between them (D4, already built).

## 5. What actually changes vs. the working nmos two-pass

Small, contained list -- this is a retarget, not a rewrite:

1. **I/O shim -> wendy2 OS ports.** The passes' file-I/O asmsubs currently
   `jsr $f018/$f024/...` (nmos stubs). Point them at the `$F800+` ports
   (the `os.p8` ABI). Isolated behind the existing shim.
2. **Target/.properties.** Build each pass with `-target wendy2.properties`
   variants: `load_address $0200`, `memtop $F000`, the same slab-base the
   nmos port uses (now landing in the mapped bank). cp437, RAW.
3. **Bank mapped at entry.** Provided by the monitor launch stub (PORTB
   `$01`); the pass must not disturb it (it only touches `$8000-$EFFF` as
   data and `$F800+` as I/O -- never the bank bits). The syslib's
   `set_upper_bank` is *not* called by the passes.
4. **Exit -> monitor.** Each pass ends by returning to the monitor (D4
   signature) so `autoexec` advances to the next pass.
5. **Disk staging.** `source.p8`, the two pass binaries, and a 2-line
   `autoexec` live on the disk; the AST file is produced/consumed there.

Everything else (the parser, codegen, arena/slab layout, the AST format)
is unchanged from the proven nmos pipeline.

## 6. Optimization: hand the AST off in a bank (skip the disk round-trip)

pass1 could write the AST into a *different* bank (say bank 2) instead of a
disk file, and pass2 read it from there -- bank RAM persists across the
pass1->pass2 reload (the monitor reloads code into lower RAM only). Saves
the ~AST-sized disk write+read. Caveat: the AST for a compiler-sized input
likely exceeds one 28 KB bank, so this needs multi-bank AST addressing
(switch among AST banks while reading). Start with the disk hand-off
(simple, unbounded); adopt in-bank hand-off only if I/O time matters.

## 7. Growth / fallbacks (if a pass outgrows the simple model)

* **Data > 28 KB high** (a pass needs more than one bank of vars/slabs):
  partition the slabs across banks and switch the window per slab region
  (each slab pinned to a known bank; a tiny accessor selects it). The
  per-sub arena reset keeps live data small, so this is unlikely soon.
* **Code > ~31 KB** (a pass's *code* reaches `$8000`): then code must be
  banked too -- the **overlay model** (separate-program phase overlays at
  `$A000`, called via `bank_call`, sharing state through a fixed-RAM ABI;
  the `.w2x` loader places them). This is the heavier path proven in
  spirit by T5/T6/D5; avoid it unless code actually overflows. Splitting a
  pass further (three passes) is an alternative that keeps each code chunk
  flat.

## 8. Verification

1. **Byte-identical self-host on wendy2c**: run the banked pipeline on
   `p1.p8` from the SPI disk; the emitted `p1.s` must equal host
   `p8c`/`prog8c` output for `p1.p8` (the same fixpoint the nmos pipeline
   checks, normalized for the `; source:` line).
2. **Corpus equivalence**: for each `.p8` in the existing self-host corpus,
   the wendy2 pipeline's `.s` equals the host oracle's.
3. **Cross-check vs nmos**: the wendy2 pipeline and the nmos pipeline
   produce the same `.s` for every input (they're the same passes; only
   the machine + I/O differ).
4. Wire a `make wendy2-selfhost` golden behind the usual skip guards.

## 9. Milestones

* **B1 -- measure.** Compile both passes for a wendy2 `.properties`
  (`memtop $F000`); confirm code top < `$8000` and total < `$F000` for each.
  (Today: pass1 17 KB / pass2 26 KB code, tops $8300/$9f00 -- both fit.)
* **B2 -- I/O shim.** Retarget one pass's file I/O to the `$F800+` OS ports;
  prove a trivial read-a-file/write-a-file on wendy2 with a bank mapped.
* **B3 -- one pass on wendy2.** Run pass1 from disk under the monitor with a
  bank mapped: read `p1.p8`, write the AST dump to disk; diff the dump vs
  the nmos pass1 output.
* **B4 -- both passes + sequencing.** 2-line autoexec runs pass1 then pass2;
  pass2 reads the AST, writes `p1.s`; diff vs the host oracle (the self-host
  fixpoint) on wendy2.
* **B5 -- corpus.** Run the curated corpus through the wendy2 pipeline; all
  byte-identical.
* **B6 (only if needed) -- capacity.** Multi-bank data and/or code overlays
  if a pass outgrows the one-bank-of-data model.

## 10. Risks / open questions

* **The exact footprints depend on the final upstream-syntax `p1.p8`** (the
  companion session's output). B1 re-measures; if pass2's high data exceeds
  28 KB, go to B6 (multi-bank data) -- but the per-sub streaming makes that
  unlikely.
* **Keeping the bank mapped vs. interrupts.** The passes run with IRQs
  masked (syslib init), so nothing repoints the bank; if an interrupt-driven
  feature is ever added, its ISR must preserve/restore the bank.
* **Monolith vs. two passes.** This plan keeps the existing two-pass split
  (each pass's code already fits the fixed region). A *single* banked binary
  would require code overlays (S7) and is not recommended.
* **AST format on disk.** Reuse the nmos pipeline's exact dump format so the
  two passes interoperate unchanged; only the I/O transport differs.
* **Slab base vs. the bank window.** Ensure the port's slab base + memtop
  land within `$8000-$EFFF` (not into `$F000` VIA / `$F800` ports). memtop
  `$F000` is the cap.

## 11. What's already built (reused as-is)

* The `wendy2` prog8 target + banking runtime (`banking.p8`) and the
  one-bank-mapped model (the launch stub maps PORTB `$01`).
* The SPI disk + `$F800+` file-I/O OS calls (`os.p8`, the `syscall_ports`
  chip, `--disk`).
* The monitor ROM with multi-line `autoexec` and return-to-monitor (D2/D4)
  -- the pass sequencer.
* The `.w2x` packager + segmented loader (D5) -- available if the overlay
  fallback (S7) is ever needed.

The new work is small and localized: the per-pass I/O-shim retarget, the
wendy2 `.properties` for each pass, the disk staging + autoexec, and the
self-host golden. The banking itself is "map a bank and run."
</content>
