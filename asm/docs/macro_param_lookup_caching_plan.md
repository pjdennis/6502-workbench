# Plan: cache macro slot-list and param-name pointers in zero page

## Problem

`ss_lookup_param_slot` (`17/macro_expansion.asm:117`) is the hot path
for resolving a parameter inside a macro body. `resolve_identifier`
(`17/expressions.asm:65-69`) calls it once per identifier mention
inside any macro expansion. The routine's first ~25 instructions
(macro_expansion.asm:117-159) **re-derive** values that are stable
for the entire lifetime of the active macro frame, on every call:

1. Read `frame_size` at frame offset 0.
2. Compute `frame_size - 2`; read 2 bytes from the frame as
   `MACRO_ENTRY16` → `HTTP16`.
3. Indirect through `HTTP16` to read `N`.
4. Compute `3*N` (`ASL` / `CLC` / `ADC`).
5. Compute `start_of_slots_offset = (frame_size - 7) - 3*N`.
6. Advance `HTTP16` past the count byte (16-bit `ADC`).

Roughly **70-80 cycles of arithmetic and indirect loads** every
identifier resolution inside a macro body, even though every input
above is fixed for the duration of that frame.

Maintenance for `MACRO_LOOKUP_FRAME16` is already O(1):

- Push: `expand_macro`'s commit path writes
  `MACRO_LOOKUP_FRAME16 := SS_P16` (`macro_expansion.asm:432-434`).
- Pop: `pop_label_scope_from_frame` restores it from the popping
  frame's scope_block (`label_scope.asm:112-117`).
- `.include` from inside a macro deliberately does NOT touch
  `MACRO_LOOKUP_FRAME16` (`expressions.asm:50-69`); the file frame
  above the macro is invisible to identifier resolution.

The optimization is to extend the same maintenance pattern to the
slot-list and param-list pointers: cache both in zero page, swap on
push/pop via the activation payload's scope_block, drop the
re-derivation from `ss_lookup_param_slot`.

## Goal

Eliminate the constant-prefix arithmetic in `ss_lookup_param_slot`.
Per-call cost shrinks to just the param-name walk plus the slot read.

Estimated savings: ~50 cycles per identifier resolution inside a
macro body. With typical macros referencing each parameter several
times in their body, this translates to a measurable speedup for any
macro-heavy assembly run (the assembler self-host included).

## Design

Two new zp pointers, two new fields in the scope_block. Both follow
the exact pattern already established for `MACRO_LOOKUP_FRAME16` /
`prev_macro_lookup`.

### New zp state (`label_scope.asm`)

```
MACRO_LOOKUP_SLOTS16:   .word
; Absolute address of slots[0] inside the innermost macro frame.
; Equal to MACRO_PAYLOAD_BASE16 at the moment expand_macro commits.
; $0000 outside any macro (SCOPE_DEPTH==0 gates use). Updated in
; lockstep with MACRO_LOOKUP_FRAME16: written on macro push, restored
; on macro pop. Read by ss_lookup_param_slot.

MACRO_LOOKUP_PARAMS16:  .word
; Absolute address of the macro definition's first parameter name --
; equal to (the active macro's MACRO_ENTRY16) + 1 (skipping the count
; byte). $0000 outside any macro. Updated in lockstep with
; MACRO_LOOKUP_FRAME16. Read by ss_lookup_param_slot. The count byte
; itself is at MACRO_LOOKUP_PARAMS16 - 1; we still read it through
; HTTP16 = MACRO_LOOKUP_PARAMS16 - 1 once per call rather than caching
; N separately (1-byte savings not worth the extra zp + scope_block
; byte).
```

Net zp delta: **+4 bytes**. (Plenty of room — the source-stack review
left zp fairly slim; recent `+2` for `SS_PEND_P16` was the only growth.)

### Scope_block grows from 7 to 11 bytes

The macro frame's scope_block today (7 bytes at offsets
`frame_size - 7 .. frame_size - 1`) is:

```
0..1 : prev LABEL_SCOPE16
2    : prev CACHED_HASH
3..4 : prev MACRO_LOOKUP_FRAME16
5..6 : MACRO_ENTRY16     (recursion detection; not restored on pop)
```

After this plan (11 bytes at offsets `frame_size - 11 .. frame_size - 1`):

```
0..1 : prev LABEL_SCOPE16
2    : prev CACHED_HASH
3..4 : prev MACRO_LOOKUP_FRAME16
5..6 : prev MACRO_LOOKUP_SLOTS16    <-- NEW
7..8 : prev MACRO_LOOKUP_PARAMS16   <-- NEW
9..10: MACRO_ENTRY16     (recursion detection; not restored on pop)
```

`MACRO_ENTRY16` STAYS at the very end (offset `frame_size - 2`) so
`check_macro_recursion` (`macro_expansion.asm:38-91`) keeps its
existing anchor without any change. `pop_label_scope_from_frame`
gains two more 2-byte loads. The new fields go in the *middle* of the
scope_block, not the end.

### `payload_size` formula update

`expand_macro:262-268` computes `payload_size = 3*N + 7`. After this
plan: `payload_size = 3*N + 11`. The frame_size guard
(`macro_expansion.asm:269-280`, `15 + name_len + 3*N <= 255`)
becomes `19 + name_len + 3*N <= 255`. With the current
`MACRO_MAX_ARGS = 32` cap and the 127-char TOKEN cap, worst-case
frame is `19 + 127 + 96 = 242` bytes -- still well below 256.

### `ss_lookup_param_slot` after the change

The constant prefix collapses to two pointer copies:

```
ss_lookup_param_slot:
  TXA
  PHA                            ; Save X (callers depend on it)

  ; Set up HTTP16 to walk the param-name list. We could read directly
  ; from MACRO_LOOKUP_PARAMS16 but the loop INYs through name bytes
  ; and INYs again for "skip past null"; HTTP16 is the easier
  ; advance-on-miss base.
  LDA MACRO_LOOKUP_PARAMS16
  STA HTTP16
  LDA MACRO_LOOKUP_PARAMS16 + 1
  STA HTTP16 + 1

  ; Read N by reaching back one byte to the count byte at
  ; (MACRO_LOOKUP_PARAMS16 - 1). Use a one-time DEC on HTTP16 and
  ; read at offset 0, then INC HTTP16 back. Or recompute via SBC #1.
  ; (Implementation detail; one cleanly-structured approach is below.)
  SEC
  LDA HTTP16
  SBC #1
  STA TEMP                       ; TEMP = count-byte addr lo (scratch)
  LDA HTTP16 + 1
  SBC #0
  STA TEMP + 1                   ; TEMP+1 = count-byte addr hi
  LDY #0
  LDA (TEMP),Y                   ; A = N
  TAX                            ; X = remaining iterations
  STA TEMP                       ; reuse TEMP as scratch (slot offset)
  LDA #0
  STA TEMP                       ; slot offset starts at 0

  ; ...same param-name walk as today (lps_iter / lps_cmp / lps_skip /
  ; lps_to_null / lps_past_null / lps_match)...

.lps_match:
  LDY TEMP
  LDA (MACRO_LOOKUP_SLOTS16),Y   ; <-- direct, no per-frame derivation
  STA IS_FWDREF
  INY
  LDA (MACRO_LOOKUP_SLOTS16),Y
  STA HEX16
  INY
  LDA (MACRO_LOOKUP_SLOTS16),Y
  STA HEX16 + 1
  PLA
  TAX
  CLC
  RTS
```

Cycle delta from the prefix:

- Removed: frame_size read + `SBC #2` + 2-byte indirect MACRO_ENTRY16
  read into HTTP16 (~22 cycles).
- Removed: `3*N` and `frame_size - 7 - 3*N` arithmetic + `PHA`/`PLA`
  for frame_size (~30 cycles).
- Removed: the post-N pointer advance from count-byte to param1
  (~14 cycles), which is now fixed-direction (one-time SBC for
  count-byte) and balanced by:
- Added: 4 bytes to copy `MACRO_LOOKUP_PARAMS16` into HTTP16
  (~10 cycles).
- Added: SBC #1 / SBC #0 to recover the count-byte address from
  PARAMS (~10 cycles) -- but see "Optional: cache count-byte addr"
  below.

Net per-call savings: **~45-50 cycles**.

### `expand_macro`'s commit path: write the cached pointers

Both values are already in zp at commit time. After the existing
anchor of `MACRO_LOOKUP_FRAME16` (`macro_expansion.asm:431-435`), add
two 2-byte stores:

```
  ; Anchor MACRO_LOOKUP_FRAME16 at the new top frame so identifier
  ; lookups inside the body resolve from this frame's slots.
  LDA SS_P16
  STA MACRO_LOOKUP_FRAME16
  LDA SS_P16 + 1
  STA MACRO_LOOKUP_FRAME16 + 1

  ; NEW: anchor the slot-list and param-list pointers so
  ; ss_lookup_param_slot doesn't have to re-derive them per call.
  ; MACRO_PAYLOAD_BASE16 still holds slot[0] from the parse loop
  ; setup; MACRO_ENTRY16 holds the macro def's count-byte address.
  CP16 MACRO_PAYLOAD_BASE16, MACRO_LOOKUP_SLOTS16
  CLC
  LDA MACRO_ENTRY16
  ADC #1
  STA MACRO_LOOKUP_PARAMS16
  LDA MACRO_ENTRY16 + 1
  ADC #0
  STA MACRO_LOOKUP_PARAMS16 + 1
```

### `expand_macro`'s scope_block write: 4 more bytes

The scope_block write at `macro_expansion.asm:381-403` writes 7
fields. Add two more, BEFORE the `MACRO_ENTRY16` write (so
`MACRO_ENTRY16` stays last in the block):

```
  ; ...existing writes for LABEL_SCOPE16, CACHED_HASH,
  ;    MACRO_LOOKUP_FRAME16...

  ; NEW: save parent's slot-list and param-list pointers so
  ; pop_label_scope_from_frame can restore them when this frame is
  ; popped. (Both are zero outside a macro -- on pop with SCOPE_DEPTH
  ; reaching 0 they go back to that.)
  INY
  LDA MACRO_LOOKUP_SLOTS16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_SLOTS16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_PARAMS16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_PARAMS16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y

  INY
  LDA MACRO_ENTRY16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_ENTRY16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y
```

### `pop_label_scope_from_frame`: restore the new fields

Today (`label_scope.asm:96-119`) the routine reads 5 bytes of
scope_block (skipping the 2-byte MACRO_ENTRY16 it doesn't restore):

```
LDY #0
LDA (SS_P16),Y          ; frame_size
SEC
SBC #7                  ; offset of activation payload start
TAY
... read 5 bytes into LABEL_SCOPE16 / CACHED_HASH /
    MACRO_LOOKUP_FRAME16 ...
DEC SCOPE_DEPTH
RTS
```

After: `SBC #11` instead of `SBC #7`, and four more byte reads:

```
LDY #0
LDA (SS_P16),Y
SEC
SBC #11
TAY
... existing 5 bytes ...
INY
LDA (SS_P16),Y
STA MACRO_LOOKUP_SLOTS16
INY
LDA (SS_P16),Y
STA MACRO_LOOKUP_SLOTS16 + 1
INY
LDA (SS_P16),Y
STA MACRO_LOOKUP_PARAMS16
INY
LDA (SS_P16),Y
STA MACRO_LOOKUP_PARAMS16 + 1
DEC SCOPE_DEPTH
RTS
```

### `init_scope_state`: zero the new pointers

`label_scope.asm:74-79` already zeroes `MACRO_LOOKUP_FRAME16`. Add
the symmetric writes for the new pointers:

```
init_scope_state:
  LDA #$00
  STA_LH16 EXPANSION_ID16
  STA SCOPE_DEPTH
  STA_LH16 MACRO_LOOKUP_FRAME16
  STA_LH16 MACRO_LOOKUP_SLOTS16   ; NEW
  STA_LH16 MACRO_LOOKUP_PARAMS16  ; NEW
  RTS
```

The zeroes are paranoia: `SCOPE_DEPTH == 0` already gates reads via
the fast path in `resolve_identifier`. But zeroing keeps debug
inspection sensible and protects against any future code that reads
the pointers without checking the gate first.

## Pointer-triple invariant

After the change, three zp pointers move in lockstep:

| Operation                       | `MACRO_LOOKUP_FRAME16` | `MACRO_LOOKUP_SLOTS16`    | `MACRO_LOOKUP_PARAMS16`     |
|---------------------------------|------------------------|---------------------------|------------------------------|
| `init_scope_state`              | `:= 0`                 | `:= 0`                    | `:= 0`                       |
| Macro push (commit)             | `:= SS_P16`            | `:= MACRO_PAYLOAD_BASE16` | `:= MACRO_ENTRY16 + 1`       |
| Macro pop                       | restored from sb       | restored from sb          | restored from sb             |
| `.include` from a macro body    | unchanged              | unchanged                 | unchanged                    |
| File pop (returning from inc)   | unchanged              | unchanged                 | unchanged                    |

Invariant: the three pointers are either **all `$0000`** (no active
macro) or **all point into the same macro frame** -- its base, its
slot region, and its def's param-name region respectively. Anything
that maintains one without maintaining the others breaks identifier
resolution silently.

This invariant should be centralized in:
1. `expand_macro`'s commit path (sets all three together).
2. `pop_label_scope_from_frame` (restores all three together).
3. `init_scope_state` (zeros all three together).

Nowhere else should touch them.

## Why caching in zp + swap (vs. recompute on every call)

Lookup frequency dominates push/pop frequency. Each macro
**invocation** does exactly one push and one pop. Each macro **body**
typically resolves several to many identifiers. Caching pays off
whenever lookups-per-invocation > break-even, which for ~50-cycle
savings per lookup vs. ~30-cycle overhead per push/pop is roughly 1
lookup per macro. Real macros average far more.

The alternative -- a per-frame zp cache populated lazily on first
lookup, invalidated on push/pop -- adds a "have I cached this yet?"
branch on every call. The eager push/pop pattern matches the existing
`MACRO_LOOKUP_FRAME16` design and shares its mechanism.

## Phasing

Per the project's small-commits TDD workflow:

1. **Add the two zp words; init in `init_scope_state`.** No reads
   anywhere yet; no scope_block changes. Full chain green. Commit.

2. **Grow the scope_block by 4 bytes** (without using the new
   space). Update:
   - `expand_macro`'s `payload_size` (`:267`): `3*N + 7` → `3*N + 11`.
   - `pop_label_scope_from_frame`'s `SBC #7` (`label_scope.asm:101`)
     → `SBC #11`.
   - `ss_lookup_param_slot`'s `SBC #7` (`macro_expansion.asm:148`)
     → `SBC #11`.
   - `check_macro_recursion`'s anchor doesn't change (still
     `frame_size - 2`).

   The new 4 bytes are reserved but not yet written or read.
   Self-host verifies. Commit.

3. **Write the new fields in `expand_macro`'s scope_block** and
   **anchor the new pointers** at commit. Restore them in
   `pop_label_scope_from_frame`. Maintained but unused. Easy to
   verify with a debug print of `MACRO_LOOKUP_SLOTS16` at the entry
   of a macro body. Full chain green. Commit.

4. **Switch `ss_lookup_param_slot` to use the cached pointers.**
   Drop the constant-prefix arithmetic. The 5 macro tests
   (parameter substitution, nested macros, recursion detection,
   scope invariants, args-at-cap) must stay green. Self-host
   verifies. Commit.

5. **Add coverage tests** (see "Test coverage" below). Commit.

Each step ends with `./asmtestgen.sh` clean and
`python3 run_tests.py -q --version 17` showing the same number of
tests it showed before (or +N for new tests in step 5).

## Test coverage

Existing tests that must stay green:

- All `macro_*` tests in `15-macros_advanced.txt` -- parameter
  substitution, fwdref propagation, multiple-arg invocations.
- `macro_args_at_cap` -- boundary on `N`. With `payload_size = 3*N + 11`
  the frame is 4 bytes larger than today; the cap is unchanged.
- `macro_recursion_*` -- pins that `check_macro_recursion`'s
  anchor at `frame_size - 2` keeps working with the larger
  scope_block.
- The four scope-invariant tests around nested macros.
- `macro_nesting_overflow` -- frame size grew by 4 bytes, so the
  OOM cascade may shift by one level. Re-baseline the expected
  traceback if needed.

New tests to add:

1. **Pointers correctly restored on nested macro pop.** A macro
   `OUTER` with a parameter `x` that invokes `INNER` mid-body, then
   references `x` again after `INNER` returns. The post-`INNER` `x`
   must resolve to `OUTER`'s slot, which means
   `MACRO_LOOKUP_SLOTS16` and `MACRO_LOOKUP_PARAMS16` were both
   restored from `OUTER`'s scope_block on `INNER`'s pop.

2. **`.include` from macro doesn't disturb the cached pointers.** A
   macro body that `.include`s a file, and the included file
   references one of the macro's parameters. The reference must
   resolve through the cached pointers (both must survive the file
   push/pop). Pins down the same invariant `MACRO_LOOKUP_FRAME16`
   has -- extended to the new pointers.

3. **Outside-any-macro state is sane.** An identifier lookup at
   file top-level (`SCOPE_DEPTH == 0`) takes the global path and
   never reads `MACRO_LOOKUP_SLOTS16` / `_PARAMS16`. Already
   covered indirectly by every non-macro test, but a focused
   assertion on `SCOPE_DEPTH == 0` is worth pinning.

## Memory map impact

| Resource              | Delta                                            |
|-----------------------|--------------------------------------------------|
| Zero page             | +4 bytes (two new pointers)                      |
| Per macro frame       | +4 bytes (two new scope_block fields)            |
| Worst-case frame_size | 246 bytes (was 242)                              |
| Code (asm.out)        | net ~ -10 to -20 bytes (lookup shrinks more     |
|                       |  than push/pop grows)                            |

The +4 bytes per macro frame is amortized -- most compiles have a
small handful of macro frames in flight at once. With
`MACRO_MAX_ARGS = 32` and the 127-char TOKEN cap, worst-case frame
is still comfortably under the 256-byte `frame_size` ceiling.

## Risks and watchouts

- **Pointer-triple invariant.** Three pointers must move together.
  Centralize maintenance in `expand_macro`'s commit path and
  `pop_label_scope_from_frame`. No other callers should touch the
  pointers. Worth an `enable_debug` assertion at
  `ss_lookup_param_slot` entry: all three are non-zero (or all
  zero); fail loudly if mismatched.

- **`MACRO_PAYLOAD_BASE16` lifetime.** Today it's a transient zp
  word used only during `expand_macro`. After this plan, the value
  it holds at commit time is the *same* as what we install into
  `MACRO_LOOKUP_SLOTS16` -- but that's a coincidence, not a
  contract. Don't be tempted to alias them permanently;
  `MACRO_PAYLOAD_BASE16` resets/reuses across nested expansions,
  while `MACRO_LOOKUP_SLOTS16` follows the active macro frame's
  lifetime.

- **`init_scope_state` symmetry.** Forgetting to zero
  `MACRO_LOOKUP_SLOTS16` / `_PARAMS16` at init won't cause a bug
  today (the `SCOPE_DEPTH == 0` gate prevents reads), but it
  clutters debug inspection and creates a latent trap if the gate
  ever weakens.

- **Step ordering during phasing.** Step 2 (scope_block growth)
  must precede step 3 (writing the new fields), or the new fields
  would land outside the reserved space and corrupt either the
  slot region (above) or `MACRO_ENTRY16` (below). The phasing
  above is the correct order; resist reordering for
  "convenience."

- **`check_macro_recursion` anchor.** Unaffected: it reads
  `MACRO_ENTRY16` from `frame_size - 2`, which stays at the very
  end of the scope_block. The new fields go in the *middle*. Don't
  reorder them to put `MACRO_ENTRY16` anywhere but last.

## Optional: cache the count-byte address too

The remaining indirect read in `ss_lookup_param_slot`'s prefix is
the back-step from `MACRO_LOOKUP_PARAMS16` to the count byte (one
SBC #1 / SBC #0 = ~10 cycles). To eliminate, also cache the
count-byte address as a third pointer (call it `MACRO_LOOKUP_DEF16`),
which equals `MACRO_ENTRY16` exactly.

Cost: +2 bytes zp, +2 bytes scope_block (frame becomes `3*N + 13`).
Saves ~10 cycles per lookup.

**Skip** unless profiling shows the prefix dominating and the count
byte is the next-largest cost. Likely overkill for the savings; the
two-pointer plan above is the right place to draw the line.

## Optional: cache N too

A 1-byte cache for the param count (`MACRO_LOOKUP_N`) would
eliminate the `LDA (count_addr),Y` read entirely (~5 cycles).

Cost: +1 byte zp, +1 byte scope_block.

**Skip** unless lookup profiling shows the count read measurable.
The two-pointer plan covers >90% of the prefix savings; further
fields have diminishing returns.

## Out of scope (for this plan, deliberately)

- **Restructuring the scope_block layout.** The two new fields go
  in between existing fields. We do not reorder, rename, or
  consolidate other fields.
- **Changing the param-name walk.** The string-compare loop
  (`.lps_iter` ... `.lps_past_null`) keeps its current shape. Any
  optimization there is a separate plan.
- **Hash-based parameter lookup.** A real hash would beat a linear
  walk for large `N`, but with `MACRO_MAX_ARGS = 32` the linear walk
  is cheap enough that the overhead of a hash isn't justified.
- **Removing `MACRO_PAYLOAD_BASE16`.** It's still needed for
  expand_macro's parse loop. After this plan it temporarily holds
  the same value `MACRO_LOOKUP_SLOTS16` will hold, but it is reset
  on every `expand_macro` call -- not the same lifetime.
