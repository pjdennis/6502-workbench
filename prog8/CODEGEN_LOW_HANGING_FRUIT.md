# Lowest-hanging fruit for p8c codegen size

Concrete, measured peephole/relaxation wins for the `p8c` backend, ranked
by effort. Numbers are byte counts from the actual `.s` output of the two
pipeline halves (`p1_pass1_sh.p8` + `p1_pass2_sh.p8`) at the current
commit. Background: [`CODEGEN_SIZE_COMPARISON.md`](./CODEGEN_SIZE_COMPARISON.md)
shows p8c emits ~1.5-1.65x upstream's code; this file is the "where do I
start" companion.

Reality check up front: the cheap wins below recover **~2.4 KB total**
across both passes (~1.2 KB/pass). That's ~10-20% of the ~10-12 KB/pass
gap to upstream. The remaining bulk is register allocation / not spilling
every subexpression through ZP -- bigger, harder, listed last.

## The enabling primitive (build this first)

Every size-dependent optimization needs **an instruction byte-sizer**: a
function mapping one emitted asm line to its length (1/2/3 bytes for
instructions by opcode+mode; operand count for `.byte`/`.word`). p8c emits
a small, fixed instruction/mode vocabulary, so this is ~50-100 lines and
fully bounded. With it (plus a label->offset map built by accumulating
sizes) you can resolve branch distances and do relaxation. It is the
leverage point -- build it once, it unlocks Tier 1 and a general peephole
pass.

## Tier 0 -- pure local peepholes (no sizing needed, trivially safe)

A single linear pass over the emitted line list (`self.out`). No address
math required.

### 0a. Drop `cmp #$00` after a flag-setting op
`lda`/`tya`/`txa`/`and`/`ora`/`eor`/`pla`/shifts already set Z and N from
their result, so a following `cmp #$00` consumed by `beq`/`bne`/`bmi`/`bpl`
is dead.

```
  lda p8v_src_eof          lda p8v_src_eof
  cmp #$00          -->    bne .Lbrs_3
  bne .Lbrs_3
```

* Sites: **106** (p1 41, p2 65). Saving: **~212 B**.
* Safety: only when the consuming branch tests Z/N (not carry). Do NOT
  apply after `jsr` (rts doesn't set flags from A) -- 41 such sites exist
  and must be left alone.

### 0b. Delete `jmp` to the immediately-following label
A `jmp L` whose very next line is `L:` is a no-op.

* Sites: **76** (p1 43, p2 33). Saving: **~228 B**.

### 0c. Thread `jmp` -> `jmp` chains
`jmp A` where `A:`'s first instruction is `jmp B` retargets to `jmp B`;
the intermediate jump often becomes unreferenced (then removed by 0b-style
dead-code sweep).

* Sites: **102** (p1 17, p2 85). Saving: small/variable, but cheap and
  composes with 0b.

Tier 0 total: **~0.45 KB**, a few hours of work, zero risk.

## Tier 1 -- branch relaxation (THE prize; needs the sizer)

Today every forward conditional emits the always-safe long form
(`codegen.py:1474-1490`): an inverted branch over a 3-byte `JMP`.

```
; if src_eof != 0 { return }            ; CURRENT (5 control bytes)
  bne .Lbrs_3
  jmp .Lendif_2
.Lbrs_3:
  jmp .Lp8s_read_dec_ret
.Lendif_2:
```

When the skipped body is within +-127 bytes (almost always -- if/while
bodies are mostly short), this collapses to a single relative branch:

```
  beq .Lendif_2                          ; OPTIMIZED (2 bytes; jmp ret stays)
  jmp .Lp8s_read_dec_ret
.Lendif_2:
```

* Sites: **707** invert+JMP idioms (p1 375, p2 332). Each in-range site
  saves 3 bytes; bodies are short enough that nearly all qualify.
  Saving: **~2.0 KB**.
* Host: `_emit_if` / `_emit_while` / `_emit_repeat` / `_emit_for` all route
  through `_emit_bool_test_branch_if_false(cond, target)` then
  `_emit_block(body)` then the end label (`codegen.py:618-640`).
* Implementation options, cheapest first:
  1. **Backpatch.** Emit the branch, record its index in `self.out`; after
     the body + end label are emitted, sum the byte-sizes between and, if
     <=127, rewrite the branch index to the short inverted form. Local,
     exact, catches every in-range site.
  2. **Conservative heuristic (no exact sizer).** Track `len(self.out)`
     across the body; if under a safe line threshold (~25 lines ~= ~55
     bytes << 127), use the short branch, else the long form. Captures
     most sites, always safe, can ship before the sizer exists.
  3. **Standalone relaxation pass.** Resolve all label offsets once, then
     collapse every in-range invert+JMP. Most general; also a natural home
     for Tier 0. Recommended once the sizer is in.

## Tier 2 -- the real gap (register/value tracking; larger effort)

The dominant cost is that **every subexpression is spilled through ZP
scratch** instead of staying in a register. Example from `read_dec`
(`val = val*10`): the 16-bit `<<` idiom round-trips the low byte through
`__p8c_wtmp0` on every shift --

```
  asl a
  sta __p8c_wtmp0
  tya
  rol a
  tay
  lda __p8c_wtmp0      ; reload what we just stored
```

A small **value-tracking peephole** (know what's currently in A/Y and in
each scratch slot; elide a `lda`/`sta` when the value is already live)
removes a large fraction of these. This is where most of the 1.5x gap
lives, but it's a proper dataflow pass, not a one-liner -- out of "lowest
hanging fruit" scope, noted here as the next frontier.

## Recommended order

1. Tier 0 peepholes (~0.45 KB, hours, no risk) -- immediate, builds the
   linear-pass scaffolding.
2. The instruction byte-sizer (the enabling primitive).
3. Tier 1 branch relaxation (~2.0 KB) -- the single biggest cheap win.
4. (Later) Tier 2 value tracking -- the bulk of the remaining gap.

Steps 1-3 recover **~2.4 KB across the two passes** and are all additive /
verifiable against the existing snapshot + self-host equivalence tests
(the output must still assemble and the pipeline must still self-host
byte-identically -- so each peephole is validated by re-running
`verify.sh`).

## Caveats

* Counts are for the current pipeline sources; they scale with program
  size as the passes grow.
* Branch-distance estimates assume short bodies; the backpatch/relaxation
  approaches measure exactly and fall back safely, so correctness does not
  depend on the estimate.
* Every change must preserve the self-host fixpoint (`p0(p1)==p1(p1)`) and
  the snapshot goldens; peepholes change bytes, so snapshots get re-blessed
  and the equivalence test is the real gate.
</content>
