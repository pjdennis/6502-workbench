# Migration plan: vasm -> the on-host (self-hosted) 6502 assembler

This document is a **gap analysis + conversion plan** for replacing the
host-side `vasm6502_oldstyle` assembler with the project's own
self-hosting 6502 assembler, so that the *entire* Prog8 toolchain --
**compiler pass 1, compiler pass 2, and the assembler** -- runs on the
6502 target (the emulator's nmos-default machine), with no external
host tools in the loop.

It is a planning document only. No code is changed by committing it.
Companion docs: [`PLAN.md`](./PLAN.md) (strategic compiler roadmap),
[`RESUME_NOTES.md`](./RESUME_NOTES.md) (session handoff),
[`README.md`](./README.md) (language surface).

---

## 1. Goal

End-state toolchain, everything running on the 6502 (emulator):

```
   source.p8
      |  p1_pass1_sh   (Prog8, runs on emulator)  -- parse + symbols -> AST dump
      v
   ast.bin
      |  p1_pass2_sh   (Prog8, runs on emulator)  -- AST -> 6502 asm text
      v
   source.s
      |  asm            (the self-hosted assembler, runs on emulator)  <-- THIS STEP
      v
   source.bin
      |  emulator
      v
   run
```

The compiler halves already run on the target: the two-pass self-host
pipeline (`p1/p1_pass1_sh.p8` + `p1/p1_pass2_sh.p8`) compiles `p1/p1.p8`
on the emulator byte-identically to the host `p8c` (see `PLAN.md`,
"Goal -- REACHED"). The **only remaining host dependency in the
runtime chain is the assembler**: today `verify.sh`, `p8c --run`, and the
tinyp8 tests all shell out to `vasm6502_oldstyle`. This plan removes that
dependency by switching to the in-tree assembler.

## 2. The two assemblers

### 2.1 vasm (current)

`p8c` emits assembly that is deliberately a subset of *both*
`vasm6502_oldstyle` and the in-tree assembler -- see the header comment in
`p8c/codegen.py:3-5` ("a strict subset of both vasm6502_oldstyle and
asm17, so we can iterate with vasm during development and switch ...").

Invocation today (`p8c/__main__.py:45-60`, `prog8/verify.sh:15-19`):

```
vasm6502_oldstyle -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc \
                  -o out.bin source.s
```

### 2.2 The in-tree assembler (target)

The self-hosted assembler now lives in `assembler2/`, restructured into
one directory per bootstrap stage `00/` .. `17/`. **The latest and most
capable version is `assembler2/17/`** (its own README calls it "ASM23").
It is a two-pass, self-hosting 6502 assembler with hash-table symbol
storage, macros, conditional assembly, and an expression evaluator. The
old flat `asm19.asm` referenced in the `codegen.py` comment is
superseded; the migration target is `17/`.

It is built by the bootstrap chain (`assembler2/asmtestgen.sh`) and runs
**on the emulator**:

```
emulator/emulator.out <asm.out> --load 2000 --input source.s --output out.bin
```

where `<asm.out>` is the assembled assembler binary produced by the chain
(`assembler2/17/out/asm.out` after a full `asmtestgen.sh` run; the chain
proves it by self-assembly).

## 3. What p8c actually emits (the assembler-feature requirements)

Inventory taken from `p8c/codegen.py` and confirmed by compiling the
whole `examples/` corpus with `--target nmos` and scanning the output.
The on-target self-host path always uses `--target nmos`, so that column
is what matters most.

| # | Emitted construct | Example | Emitted by nmos target? |
|---|---|---|---|
| R1 | Origin / PC set | `.org $0200`, `.org $F0C0`, `.org $FFFC` | yes (codegen.py:64,87,93,288) |
| R2 | Byte data, comma lists, decimal + hex + quoted strings + `,0` terminator | `.byte 0, 1, 2`, `.byte "total=", 0` | yes |
| R3 | 16-bit word with a symbol | `.word p8s_main` | yes (reset vector) |
| R4 | Constant / EQU assignment | `__p8c_tmp0 = $20`, `p8v_main_i = $40` | yes |
| R5 | Low/high byte selector | `lda #<p8c_str_0`, `ldx #>p8c_str_0` | yes |
| R6 | **Label + offset arithmetic in operands** (pervasive: every 16-bit hi-byte access, indexed data) | `sty p8v_main_p+1`, `adc __p8c_wtmp0+1`, `sta p8st_toks+2,y` | yes |
| R7 | Decimal literals | `.byte 0, 0, 0` | yes |
| R8 | Addressing modes: imm, zp, abs, abs,Y, (zp),Y, (zp,X), abs,X, zp,X/Y, JMP () | `lda (__p8c_ptr0),y` | yes |
| R9 | Dot-prefixed local labels, globally unique | `.Lfor_top_0:`, `.Lhalt_p8s_main:`, `.__mul_loop:` | yes |
| R10 | Quoted-string escapes pre-lowered to hex bytes by codegen | `.byte "...", $0d, 0` | yes (codegen self-escapes, codegen.py:298-319) |
| R11 | `bcc *+3` -- PC-relative skip (uword 16-bit negate idiom) | `bcc *+3` / `iny` | yes, **iff** a program uses uword unary `-` (codegen.py:931) |
| R12 | `bra` (65C02) halt loop | `bra .Lhalt_main` | **no** -- nmos main exits via `lda #$00 / jsr $f00f / brk` (codegen.py:382-392). `bra` is **wendy2c-only**. |

Things p8c **never** emits (so the assembler need not support them):
binary `%` literals, parentheses in expressions, `& | ^ *` operators,
macros, conditional assembly, `.align`/`.fill`. All compile-time
arithmetic (struct offsets, `<label`/`>label` of array elements, etc.)
is folded by codegen before emission.

## 4. ASM23 (`assembler2/17/`) capabilities vs. those requirements

Verified against `17/directives.asm`, `17/expressions.asm`,
`17/instruction_tables.asm`, `17/labels.asm`, `17/from_decimal.asm`,
`17/forward_ref.asm`, and the `17/tests/` corpus.

| Req | ASM23 support | Verdict |
|---|---|---|
| R1 origin | **`* = $addr` only** -- there is no `.org` directive | **GAP-A** |
| R2 `.byte` comma/decimal/hex/strings + `,0` | `.byte` with comma-separated mixed decimal/hex/string operands (directives.asm:36,104,257-264) | OK |
| R3 `.word symbol` | `.word`, little-endian (directives.asm:108) | OK |
| R4 `LABEL = value` | yes (labels.asm:158-174) | OK |
| R5 `#<label` / `#>label` | yes (expressions.asm:196-230) | OK |
| R6 `label+offset` in **all** operand positions | `+` and `-` evaluated in every operand position incl. `(ptr+$02),Y`, `abs+N`, `abs+N,Y` (expressions.asm:276-393; tests 03-expressions_operators) | OK |
| R7 decimal | yes (from_decimal.asm) | OK |
| R8 addressing modes | all NMOS modes incl. (zp),Y / (zp,X) / abs,Y / JMP() | OK |
| R9 dot-local labels | local labels scoped to the preceding global label (label_scope.asm); p8c names are globally unique and always follow a global (`p8s_*:` / `__p8c_*:`) so no collision | OK |
| R10 string escapes | not needed -- codegen pre-lowers escapes to `$XX` bytes; `.byte "...", $0d` assembles fine | OK |
| R11 `bcc *+3` | **`*` is valid only as the PC-assignment target (`* = ...`), not inside an operand expression** (no current-PC term in expressions.asm) | **GAP-B** |
| R12 `bra` halt | **NMOS-only opcode table -- no `bra`/`phx`/`stz`/...** (instruction_tables.asm) | **GAP-C** (wendy2c only) |

**Net: of everything p8c emits, only three constructs are unsupported,
and only two of them (GAP-A, GAP-B) occur on the nmos self-host path.**
The pervasive, scary-looking requirement -- `label+offset` arithmetic on
every 16-bit operation -- is fully supported (R6).

## 5. Resolving each gap

All three fixes are *also* accepted by `vasm6502_oldstyle`, so they
**narrow** the single emitted dialect rather than forking it. We keep the
"subset of both assemblers" property and can still iterate with vasm.
Preferred approach: change **codegen**, leave the assembler untouched.

### GAP-A -- `.org` -> `* =`
`vasm6502_oldstyle` accepts `* = $addr` for PC assignment, so emitting
that form instead of `.org` loses nothing on the vasm side and gains
ASM23. Four emission sites in `codegen.py` (prologue x2, string-pool
reloc, reset-vector). Trivial.
Alternative (rejected): add `.org` as an alias in ASM23's directive
table -- more invasive, and forks the assembler's own dialect.

### GAP-B -- `bcc *+3` -> labeled skip
Replace the one PC-relative idiom (16-bit negate, codegen.py:929-932)
with a generated unique local label:

```
  bcc .Lskip_N
  iny
.Lskip_N:
```

vasm-compatible and ASM23-compatible. One small codegen edit.

### GAP-C -- `bra` halt (wendy2c target only)
Not on the nmos self-host critical path. When/if the wendy2c target is
brought onto the on-host assembler, replace `bra .Lhalt` with NMOS
`jmp .Lhalt` (3 bytes, universally accepted). Optional for the
self-host milestone.

### Stale comment cleanup
`p8c/codegen.py:3-5,76,300` and `p8c/__init__.py:6` still say "asm17".
Update to reference `assembler2/17/` (ASM23) as the on-host target.

## 6. Migration steps (phased; each step independently testable)

**Phase M0 -- narrow the emitted dialect (codegen only).**
Apply GAP-A and GAP-B (and GAP-C if wendy2c is in scope). After this,
every `.s` p8c emits is accepted by *both* vasm and ASM23. Gate: the
existing host test suite (snapshots/codegen/e2e under vasm) stays green,
i.e. the dialect change must not alter assembled bytes. Re-bless the
`.expected.s` snapshots for the `.org`->`*=` text change.

**Phase M1 -- build + wrap the assembler.**
Run `assembler2/asmtestgen.sh` to produce `assembler2/17/out/asm.out` and
confirm self-assembly. Add a thin wrapper, e.g.
`prog8/tools/asm_onhost.sh src.s out.bin`, that runs
`emulator/emulator.out 17/out/asm.out --load 2000 --input src.s --output out.bin`.

**Phase M2 -- second assembler backend in p8c.**
In `p8c/__main__.py` add `run_onhost_asm()` beside `run_vasm()` and a
`--asm {vasm,onhost}` flag (default `vasm` during transition). `--run`
honours it.

**Phase M3 -- equivalence sweep.**
For the whole corpus (`examples/`, `snapshots/`, `tinyp8/`, and the
`p1/` pipeline `.s`), assemble with both backends and diff the binaries.
Resolve any differences (see Risks -- expect differences only in
trailing zero-fill extent around the `$FFFC` reset vector, which should
be normalized or matched, not hand-waved).

**Phase M4 -- flip the on-target chain.**
Switch `prog8/verify.sh` (and the tinyp8 `test_e2e` / `test_self_host` /
`test_v2`) from vasm to the on-host assembler. Add an end-to-end driver
that chains all three emulator runs:
`p1_pass1_sh` -> AST -> `p1_pass2_sh` -> `.s` -> `asm` -> `.bin` -> run.
This is the deliverable: **passes 1 and 2 and the assembler, all on
target.** Gate: byte-identical to the current host-assembled result.

**Phase M5 -- make on-host the default; retire vasm.**
Flip the `--asm` default to `onhost`; keep `vasm` selectable as an
oracle. Update docs (`PLAN.md` Phase 7, this file, README ABI note).

## 7. Validation strategy

1. **Dialect-neutral bytes (M0):** assembled output under vasm must not
   change when codegen switches `.org`->`*=` and `*+3`->label. Snapshot
   `.expected.s` diffs cover the text; the e2e LCD/stdout goldens cover
   the bytes.
2. **Cross-assembler binary equivalence (M3):** `vasm(s) == onhost(s)`
   for every corpus `.s`, modulo a defined normalization for reset-vector
   zero-fill length.
3. **Self-host equivalence preserved (M4):** the existing 0-line
   `verify.sh` diff (`p0(p1.p8) == p1(p1.p8)`) must still hold with the
   on-host assembler in the loop.
4. **End-to-end goldens (M4):** each corpus program, assembled on-target
   and run, produces its expected LCD/stdout frame.

## 8. Risks / open questions

* **R-FWDREF (highest risk) -- forward-reference table capacity.**
  ASM23 records **one entry per forward-referenced use-site** in a fixed
  list `FWDREF_LIST = $0200..$03FF` (512 bytes => ~255 entries;
  `17/asm.asm:13-14`, `17/forward_ref.asm`). The list is *rewound*
  between passes, not compacted, so the cap is the **total number of
  forward references in the whole program**, and overflow raises
  `err_too_many_forward_refs` (code 37). Machine-generated p8c output is
  forward-reference-heavy (forward `if`/`while`/`for` skips via the
  long-branch invert+JMP pattern, calls to subs defined later, the
  string pool and reset vector at the end). A compiler-sized program like
  the `p1` pipeline `.s` may well exceed 255.
  - **Action:** empirically assemble the `p1_pass1_sh` / `p1_pass2_sh`
    `.s` (and `tinyp8.p8`'s `.s`) with ASM23 *first*, before committing
    to the swap, and read the debug forward-ref count
    (`enable_debug` build prints it).
  - **Mitigations if it overflows, cheapest first:** (a) enlarge
    `FWDREF_LIST` into the free `$0400-$05FF` region (the memory map
    marks it free) -- 4x headroom for a one-line change; (b) reduce
    forward refs in codegen (emit the string pool *before* code; order
    helper subs before callers); (c) deeper: drop the per-site list
    entirely by making forward refs deterministically absolute in both
    passes (a true two-pass model needs no list) -- the largest change,
    but removes the cap permanently.

* **R-HEAP -- label/heap capacity.** Hash table is 128 buckets chained on
  the heap ($2000+ up to the source stack at $F000, with a 256-byte
  safety gap). A large `.s` has many labels; confirm the heap doesn't
  collide with the source stack (`err_out_of_memory`, code 35). Validate
  on the `p1` pipeline `.s`.

* **R-FILL -- reset-vector binary length.** With `* = $0200 ... * = $FFFC
  .word entry`, ASM23 zero-fills forward to $FFFC (output.asm
  `advance_pc_to_hex16`), yielding a ~64 KB image -- same shape vasm
  produces today. Confirm the emulator's load/size handling matches
  between the two backends; define the M3 normalization accordingly.

* **R-TOKEN -- identifier length.** ASM23 caps tokens at 127 chars
  (`err_token_too_long`). p8c mangled names are short; low risk, but
  worth a guard/check.

* **Open:** does the wendy2c target join this migration, or only nmos?
  The self-host milestone needs only nmos; wendy2c adds GAP-C plus its
  `.include`d `.inc` library files, which must themselves assemble under
  ASM23 (they are hand-written for vasm and may use unsupported
  constructs). Recommend: nmos first, wendy2c as a follow-on.

## 9. Bottom line

The assembler gap is **small and well-bounded**. On the nmos self-host
path there are exactly two syntactic gaps (`.org`->`*=`,
`bcc *+3`->labeled skip), both fixable with a few lines in codegen and
both still vasm-compatible. The real engineering risk is not syntax but
**capacity** -- principally the ~255-entry forward-reference table --
which must be measured against the real `p1` pipeline `.s` before the
swap is trusted. Once M0-M4 land, the full Prog8 toolchain (pass 1, pass
2, assembler) runs end-to-end on the 6502 with no host assembler.
</content>
</invoke>
