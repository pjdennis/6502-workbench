# Codegen size: p8c vs. upstream prog8 (headroom measurement)

A measurement of how much smaller the pipeline binaries would be if our
`p8c` backend generated upstream-quality 6502 code. Motivation: the
two-pass `p1_pass1_sh` / `p1_pass2_sh` split exists because the monolith
doesn't fit one 64 KB binary; this quantifies how much of that pressure
is *codegen quality* rather than fundamental program size.

Companion docs: [`PLAN.md`](./PLAN.md), [`RESUME_NOTES.md`](./RESUME_NOTES.md),
[`ASM_MIGRATION_PLAN.md`](./ASM_MIGRATION_PLAN.md).

## Method

Both pipeline halves were compiled two ways and the resulting 6502
binaries measured:

* **p8c** (our compiler): `python3 -m p8c --target nmos p1/<pass>.p8 -o x.s`
  then `vasm6502_oldstyle -Fbin` -> binary.
* **upstream prog8c** (`prog8c-12.1.1-all.jar`, optimizer on by default):
  via the repo's own `upstream/port_pipeline.py` (which ports the source
  to upstream-legal Prog8 and **slabs the >256-element arenas into RAM**),
  then `java -jar prog8c.jar -target nmos.properties` -> 64tass -> binary.

To compare **codegen** and not data layout, each binary was split into
**code (instruction bytes)** vs **reserved data / arenas / string pool**
using the vasm and 64tass listings. p8c reserves its node/symbol arenas
*in-image*; the upstream port moves them to RAM -- so the arenas are
excluded on both sides for an apples-to-apples read.

Toolchain was built/fetched into an ephemeral container: vasm 2.0e (from
source), 64tass 1.59.3120 (apt), `prog8c-12.1.1-all.jar` (GitHub release).
Reproduce with `upstream/selfhost.sh` (upstream side) and
`p8c + vasm6502_oldstyle` (p8c side).

## Results -- code only (instruction bytes, identical source)

| pass | p8c | upstream | p8c / upstream | recoverable |
|------|-----|----------|----------------|-------------|
| pass 1 | 27,068 B | 16,453 B | **1.65x** | ~10.6 KB (-39%) |
| pass 2 | 34,642 B | 22,357 B | **1.55x** | ~12.3 KB (-35%) |

**p8c emits ~1.5-1.65x as much code as upstream for the same source.**
A mature optimizing backend could remove on the order of **35-40% of the
generated code**.

### Full image segments (what consumes the ~60 KB budget)

| pass | p8c `$0200` seg | of which in-image arenas/overflow | p8c pool (@`$F0C0`) | upstream raw `.bin` (arenas in RAM) |
|------|-----------------|-----------------------------------|---------------------|--------------------------------------|
| pass 1 | 30,520 B | 3,452 B | 312 B | 17,115 B |
| pass 2 | 38,882 B | 4,240 B | 3,299 B | 26,214 B |

## Implications

The gap is large enough to change architecture, not just free a few bytes:

* The two-pass split exists because the monolith's front-end (~22 KB) +
  codegen (~33 KB) ~= **55 KB of code** can't co-reside in the ~60 KB
  window. At the upstream code ratio (~0.62x), **55 KB -> ~34 KB**. With
  arenas slabbed to RAM (which the upstream port already does), a
  ~34 KB-code monolith plus pools would plausibly **fit in a single
  binary** -- i.e. upstream-quality codegen could theoretically dissolve
  the pass1/pass2 split entirely.
* Per pass, recovering 10-12 KB takes each binary from "hundreds of bytes
  free" to multi-KB headroom, easing the constant fight to land each new
  codegen feature.

## Where the bloat is (the recoverable part)

Standard unoptimized-codegen tax, none of it fundamental:

* No peephole pass.
* Every expression spilled through ZP scratch instead of kept in
  registers.
* Long-branch `invert + JMP` on **every** forward conditional (+3 bytes
  each, always -- even where a 2-byte relative branch would reach).
* Redundant load/store around 16-bit ops.
* No common-subexpression / dead-store elimination.

## Caveats

1. **Same logic, slightly different data shape.** The upstream side
   compiles the *ported* source (arenas -> RAM peek/poke); that alters
   array-access code slightly, but not the bulk of the comparison.
2. Upstream runs with its optimizer on (its default) -- "best-case
   upstream," the right reference for a *theoretical headroom* question.
3. The code/data split relies on listing parsing and treats upstream's
   trailing `.fill` (~2.4 KB, confirmed as BSS beyond the `.bin` top
   `$44DB`) as RAM, not image -- consistent with how p8c's in-image
   arenas were excluded.
4. Numbers are for the `p1_pass1_sh.p8` / `p1_pass2_sh.p8` pipeline
   sources at the current commit; they will drift as the passes grow.
</content>
