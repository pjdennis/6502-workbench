# Plan: self-host the *monolith* p1.p8 on wendy2 using banking

> **STATUS: ACHIEVED.** The single-binary monolith, built for wendy2c and run
> on the emulator, compiles its own ~6300-line source to assembly
> **byte-for-byte identical** to the host p8c oracle (41058 lines), exiting
> cleanly (STP) after ~11.25 G cycles / ~18 min. sym/node/cons live in a second
> RAM bank (logical bank 1) reached via a fixed-high-RAM ($F810/$F830/$F850/
> $F870) bank-switch accessor; ident/str slabs + code + BSS live in bank 0.
> Gated regression test: `P1WendySelfHost` (set `P1_WENDY_SELFHOST=1`).


Run the **single-binary** monolith compiler (`p1/p1.p8` — lex + parse +
codegen in one program, no inter-pass disk hand-off) on the **wendy2c**
machine, reproducing its own host-compiled `.s` byte-for-byte (the
self-host fixpoint), reading source / writing output over the simulated
SPI disk.

This is the **monolith** counterpart to
[`WENDY2_SELFHOST_BANKING_PLAN.md`](./WENDY2_SELFHOST_BANKING_PLAN.md)
(which banks the two-pass split). The user chose the single binary.

---

## 1. The sizing reality (measured, not estimated)

Built with **upstream `prog8c` v12.1.1** (the compiler that produces the
wendy2 binary), the monolith is far smaller than the p8c+vasm build:

| build                          | code + init-data        | with BSS top |
|--------------------------------|-------------------------|--------------|
| `prog8c` nmos (6502)           | 38438 B `$0200-$9825`   | ~`$A8F7`     |
| `prog8c` wendy2 (65c02, memtop `$F000`) | 36984 B `$0200-$9277` | ~`$A34A`     |
| p8c + vasm (Python codegen)    | ~`$EFC0` (≈ 56 KB)      | n/a          |

The p8c+vasm codegen is ~2.5× more verbose than upstream. **The wendy2
binary is built by upstream `prog8c`**, so the number that matters is
**37 KB code+data**, topping ~`$A34A` with today's (tiny) arenas.

### Key consequence: NO code overlays

wendy2c memory with one RAM bank held mapped (PORTB `$01`):

```
  $0000-$7FFF  fixed lower RAM   (code + low data + ZP + stack)
  $8000-$EFFF  the mapped bank   (28 KB)  <- upper code + data + arena slabs
  $F000-$F7FF  VIA
  $F800-$FFFF  fixed high RAM + OS-call ports ($F800-$F80F) + vectors
```

Code+data (37 KB) reaches only to ~`$9277`, i.e. ~4.6 KB into the held
bank. Everything from `$A34A` up to `$EFFF` (~**19 KB**) is free for the
growable arenas. So `$0200-$EFFF` behaves exactly like the nmos flat
layout (`load $0200`, `memtop $F000`) with the top 28 KB supplied by one
held bank — **no per-access bank switching, no overlays**, just like the
split plan, because the monolith's *code* (unlike its p8c build) fits.

The single-binary monolith is therefore viable on wendy2 with the same
"map one bank and run" model. Code overlays (the heavy `bank_call` path)
are a fallback only if a self-host input needs arenas > ~19 KB and we
can't fit them in one bank (then: multi-bank data, S6).

## 2. Why arenas must become peek/poke slabs

To self-host, the monolith must hold the symbol/sub/ident/string tables
for the whole ~6000-line `p1.p8` input, far past today's array caps
(node 60, sym 32, sub 32, cons 60, str_pool 208 B, ident_pool 120 B).
prog8 arrays cap at 256 elements, so anything bigger must move to raw-RAM
**peek/poke slabs** at absolute addresses (the technique the `_sh` chain
already uses at `$8c52..$ea88`). Per-sub node/cons arenas reset each sub,
so only the *persistent* tables (sym, sub, ident_pool, str_pool, their
offset tables) grow large; node/cons stay bounded by the biggest single
sub.

### The build-tool consequence (important)

Slabs sit at fixed absolute addresses. They fit **only in the upstream
build** (code tops `$9277`, slabs go `$A400+`). They do **not** fit in
the p8c+vasm build (code already reaches `$EFC0`). So the corpus
equivalence test must build the monolith with **upstream `prog8c`**, not
p8c+vasm. This is sound: a binary built by upstream emits exactly the
same `.s` as one built by p8c+vasm (verified — byte-identical on the
emulator), because the monolith's *codegen logic* is independent of how
the monolith binary was compiled. Upstream is also the real wendy2 build
path, so the test then exercises what ships.

## 3. What changes vs. the working nmos monolith

1. **Corpus build → upstream prog8c.** Switch `P1Equivalence.setUpClass`
   to build `p1.p8` with `prog8c -target nmos.properties` + `mkimage.py`
   (instead of p8c+vasm). Validated byte-identical already. (M1)
2. **Arena slab conversion.** Move the persistent tables (and, as needed,
   node/cons) to peek/poke slabs at absolute upper addresses; grow caps
   past 256. Corpus stays green throughout (small inputs). (M2)
3. **I/O shim → wendy2 OS ports.** The I/O asmsubs currently
   `jsr $f012/$f018/$f021/$f024/...` (nmos stubs). Retarget to the
   `$F800+` OS-call ABI (`os.p8`): clear/append filename, open-r/open-w,
   select-handle, read/eof/write, close, poweroff. Isolated to ~6
   asmsubs at the top of `p1.p8`. Kept behind a build switch so the same
   source still builds the nmos binary for the corpus test. (M3)
4. **No argv on wendy2.** The nmos build gets the source/output paths from
   `sys_argv`. wendy2 has no argv: the monitor/autoexec convention passes
   fixed filenames (e.g. `IN.P8` / `OUT.S`) on the SPI disk. The argv
   shim becomes "return the fixed staged names." (M3)
5. **Target/.properties.** A wendy2 monolith `.properties` (65c02, cp437,
   RAW, `load $0200`, `memtop $F000`, freestanding/own-I/O). (M3)
6. **Bank mapped at entry + exit to monitor.** Provided by the monitor
   launch stub (PORTB `$01`); the monolith only touches `$8000-$EFFF` as
   data and `$F800+` as I/O, never the bank bits. Exits via `$F80F`
   (poweroff) or the monitor return signature. (M4)

Everything else (parser, codegen, AST format) is unchanged.

## 4. Milestones

* **M1 — corpus build → upstream. DONE.** `P1Equivalence` builds the
  monolith with upstream `prog8c` + `mkimage.py`; corpus byte-identical.
  (Unblocked slabs AND the asmsub/extsub feature -- the headroom the flat
  p8c+vasm build lacked.)
* **M3 — wendy2 retarget. DONE.** `%address` dropped (load address from
  the target); I/O extracted into a per-target `sysio` module (nmos $F006
  asmsubs / wendy2 $F800 disk ports + fixed in.p8/out.s names); wendy2
  monolith `.properties` (65c02, load $4000, memtop $F000). nmos binary
  byte-identical (corpus 32/32). Two emulator fixes: serial RX queue sized
  to a full program, and disk rewind-on-EOF so the multi-pass reader
  re-scans (reset_source just clears its flag).
* **M4 — monolith on wendy2. DONE.** The monolith built for wendy2c and
  run on the emulator (held bank $01, $F800 disk I/O) reproduces p8c's .s
  byte-for-byte. New emulator `--wendy2-prog` preloads the RAW program
  straight into RAM (bank $01) and starts it -- the serial boot is far too
  slow for ~38 KB. Regression test: `P1WendyEquivalence` (12-program
  cross-section), each byte-identical.
* **M2 — slab conversion. NEXT.** Convert persistent tables to peek/poke
  slabs at absolute addresses; raise caps past 256. Corpus green after
  each arena. (Self-host capacity; also the user's explicit ask.) Now also
  feeds M6 -- the slabs are what get partitioned across banks.
* **M5 — self-host fixpoint on wendy2.** Compile `p1.p8` itself on
  wendy2; emitted `p1.s` equals host `prog8c`/p8c output (normalized for
  `; source:`). Needs M2 (capacity) + M6 (the ~24 KB of slabs exceed one
  bank, S6). Wire `make wendy2-mono-selfhost` behind skip guards. Also
  needs the monolith to PARSE its own dialect fully (it already handles
  qualified calls like strings.compare / sysio.* via the parser, but
  %import handling for self-parse is unverified -- shake out at M5).
* **M6 — multi-bank data (now primary, not "only if needed").** p1.p8's
  ~24 KB persistent slabs exceed the ~22 KB free in one held bank (S6), so
  partition: sym/sub/node/cons in the default bank, ident_pool/str_pool in
  a second bank with switching accessors.

## 5. Feature completeness (parallel prerequisite)

The monolith still lacks `asmsub`/`extsub` with `@REG` ABI, which
`p1.p8`'s own source uses (sys_* I/O). This must land for the self-host
(M5) regardless of banking. Slab conversion (M2) frees main-address-space
headroom that the flat monolith lacked, unblocking this feature work. Port
from the `_sh` chain (`reg_code`, `parse_param @REG`, `parse_ret`,
`parse_asmsub`, `parse_extsub`, asmsub-body codegen, regabi call ABI).

## 6. Risks / open questions

* **One-bank capacity — MEASURED, INSUFFICIENT.** Compiling p1.p8 itself
  needs (measured via p8c on the real source): **237** subs, **265**
  module vars, a **~770-entry** persistent sym-table peak (module vars +
  223 params + 282 scalar locals). At ~14 B/sym that sym table alone is
  ~11 KB; with the sub table (~1.4 KB), ident_pool (~7 KB) and str_pool
  (~5 KB) the persistent slabs total **~24 KB** — past the ~22 KB free in
  one held bank (code+data top ~$9795). So the monolith self-host needs
  **multi-bank data (M6), not the one-bank model.** (The `_sh` chain's
  sym table is likewise sized ~780 entries; it only fits flat-64K because
  each split pass holds far less code AND its slabs reach to ~$EA88.)
  Per-sub-resetting *locals* (keeping only module vars + all params +
  one sub's locals persistent) would shave the sym table ~3.8 KB but not
  enough to reach one bank — multi-bank is the robust answer.
* **Multi-bank partition (M6 made primary).** Pin each slab region to a
  known bank: e.g. bank 0 (default-mapped) holds sym + sub + node + cons;
  a second bank holds ident_pool + str_pool. The ident/str accessors
  switch the window to their bank, peek/poke, switch back — frequent but
  localized. node/cons (per-sub reset, transient) and the sym/sub tables
  (hottest) stay in the default bank to avoid switching on the hot path.
* **Slab base vs. the bank window.** Slab base + memtop must land within
  `$8000-$EFFF`, clear of `$F000` VIA / `$F800` ports. `memtop $F000`
  caps it.
* **Keeping one build source.** The nmos corpus build and the wendy2
  build differ only in the I/O shim + `.properties`. Keep the I/O
  difference behind one small, swappable shim so a single `p1.p8` serves
  both (no forked sources).

## 7. What's reused as-is

* The `wendy2` banking runtime + one-bank-mapped launch (monitor maps
  PORTB `$01` before jumping to a loaded program).
* The SPI disk + `$F800+` OS-call file I/O (`os.p8`, `syscall_ports`
  chip, emulator `--disk`).
* The monitor ROM with multi-line `autoexec` + return-to-monitor.
* `mkimage.py` (reset-vector wrap) and the upstream build invocation
  (`cd upstream && prog8c -target … -out W ../p1/p1.p8`).
