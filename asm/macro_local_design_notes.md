# Macro-Local Optimization: Design Notes

Status: deferred. Tackle **after** parameter activation-frame work is done.
This doc captures the design we agreed on so we can come back to it cold.

## Goal

Eliminate the per-invocation heap leak for macro-local (`.label`) labels
without introducing cross-pass persistent state for them. Today, every
macro-local label in every invocation gets an LHASHTAB entry that lives
until end-of-assembly; over a large codebase this is the dominant
heap-pressure source after parameters.

The chosen approach is **Option 3: pre-scan the body in both passes**.
Pass 1 and pass 2 do identical work for macro-locals; nothing about a
macro expansion outlives the expansion.

## Why a single-walk approach doesn't work

Pass 2 emits in stream order. When it hits `JMP .skip` before `.skip:`
is defined later in the body, it needs `.skip`'s value to encode the
operand. Today this works because pass 1 wrote `.skip` into the hash
under an `EXPANSION_ID` synthetic scope, and the entry survives into
pass 2. If we free macro-local state at end of expansion, pass 2 has
nothing to read.

Persisting a tighter per-invocation slot list across passes works
(option A in the discussion) but still leaks O(invocations). Pre-scan
in pass 2 only (option B) recomputes values without persistence but is
asymmetric. Option 3 makes both passes symmetric.

## The key insight

For an in-body macro-local reference, the property "is this reference
forward of its definition?" is a **static property of the macro body**.
It does not depend on values, args, or which pass we're in. If both
passes apply the same static rule locally, neither needs to tell the
other anything via FWDREF_LIST.

So: each pass independently pre-scans + real-walks each invocation,
making the same encoding decisions, populating the same slot table.
No cross-pass channel for macro-locals.

## Mechanism per invocation (identical in both passes)

1. **Pre-scan body**: walk in order, advance PC, fill macro-local slots
   as `.label:` is encountered. When sizing an instruction whose
   operand is a macro-local that has not yet been seen in this walk →
   assume ABS (size 3). For nested macro invocations, recursively
   pre-scan to size them (see "Nested invocations" below).
2. **Real-walk body**: walk in order again with PC reset to start of
   expansion. Track "defined-so-far in this walk" — a small bitmap or
   position counter per slot. At each macro-local reference:
   - Definition not yet encountered in this walk → encode ABS,
     operand value comes from the pre-scanned slot.
   - Definition already encountered → use slot value to choose ZP vs
     ABS as for any constant.

Pre-scan and real-walk apply the same "is the definition behind me?"
rule. Pre-scan applies it for sizing only; real-walk applies it again
for the same sizing decision but also has values to emit.

The two passes differ only in what real-walk records:
- Pass 1 real-walk: capture global label values, advance PC, no byte
  emission (matches current pass-1 behavior).
- Pass 2 real-walk: emit bytes.

## What this eliminates

- **`LABEL_TYPE_MACRO_LOCAL`** — gone.
- **`EXPANSION_ID16`** and the synthetic-scope mechanism for
  macro-locals — gone. (Parameters already moved to frames in the
  earlier work, so EXPANSION_ID may already be gone by then.)
- **Hash entries for macro-local labels** — gone. They live entirely
  in the activation frame slot table.
- **FWDREF_LIST entries for in-body macro-local refs** — not needed.
  Size decisions are made by the static "defined-so-far" rule, applied
  identically in both passes.

## What still persists across passes

- Global label values (LHASHTAB) — fundamental.
- FWDREF_LIST — only for refs to **global** labels not yet defined.
  Those genuinely need cross-pass communication.
- Macro definitions on the heap, including a definition-time-recorded
  list of macro-local label names (added by this work — pre-scan the
  body once at `.macro` time to collect names + assign slot indices).

## Frame layout (extends the merged file/scope/activation stack)

For a memory-source frame (macro expansion), in addition to the
parameter slots from the earlier work:

```
... existing source-frame fields (name, types, prev_line) ...
prev_macro_frame_L/H            chain to enclosing macro frame
macro_def_ptr_L/H               for parameter and macro-local name lookup
arg_count                       (or derive from def)
local_count                     (or derive from def)
slots[0 .. arg_count + local_count - 1]:
    value_L, value_H, fwdref_flag    (3 bytes each)
defined_bitmap                  (real-walk "defined-so-far" tracking;
                                 1 bit per macro-local slot, transient)
... existing source-frame trailer (handle or mem_ptr) ...
```

Notes:
- Parameters and macro-locals share the same slot shape — only the
  fill timing differs (parameters at push, macro-locals during
  pre-scan / real-walk).
- Names are not duplicated in the frame. The macro definition
  records them once with stable indices; identifier lookup scans the
  def's name list and uses the matched index to read the slot.
- An empty/uninitialized slot needs a sentinel. A separate "filled"
  bitmap or a reserved fwdref_flag value works. A reference to an
  unfilled slot at end-of-pre-scan is "label not defined in this
  expansion" — error, same as any undefined label.

## Nested macro invocations

This is the part most likely to bite. The naive approach
(recursive pre-scan-then-real-walk per invocation) compounds badly
with depth.

**The fix**: pre-scan **pushes nested frames and does not pop them**.
Real-walk encounters those invocations in the same order, finds
their frames already pre-scanned, and proceeds straight to real-walk.

Concretely, during A's pre-scan when we hit invocation B:
1. Capture B's args from the current expression context.
2. Push B's frame.
3. Recursively pre-scan B's body (filling B's slots; recursing
   further into any of B's nested invocations).
4. **Do not pop B's frame.**
5. Continue A's pre-scan past B's invocation.

When A's real-walk reaches the same invocation point:
1. B's frame is already on the stack (top of the nested chain at
   this point in body order).
2. Skip B's pre-scan; do B's real-walk directly.
3. Pop B's frame at end of B's real-walk.

Each invocation in the entire tree is pre-scanned once and
real-walked once → total work is ~2× the original, regardless of
nesting depth. The frame stack temporarily holds the entire nested
tree of expansions during the outer pre-scan.

Determinism for arg evaluation: when pre-scan evaluates B's args, it
may reference outer-frame parameters and outer macro-locals. Those
are available because A's frame is on the stack and pre-scan has
been filling A's slots in order. Pass 1 pre-scan and pass 2 pre-scan
see identical state at this point (PC trajectory is deterministic),
so B's args are captured identically in both passes.

## Identifier lookup inside a macro body

After both this work and the parameter work:

1. Walk active macro frames innermost-first via `prev_macro_frame`
   chain. For each frame, scan the macro definition's name list
   (params + macro-locals); on match, read the slot.
2. Hash: locals under the enclosing global, then globals.

Macro-local refs always use absolute mode for ZP-vs-ABS unless
backward-resolved with a value < $100. Branch and JMP absolute
encodings are unaffected (those are always REL or ABS regardless).

## Subtleties / watchouts

- **Conditional definitions inside the body** (`.label:` inside
  `.ifdef`): the macro def's name list is the static set of names
  that *could* be defined. At invocation time, conditionally-skipped
  definitions leave their slots unfilled. A reference to an unfilled
  slot must error as "label not defined" — not silently fall through
  to globals (typo masking).
- **Pass-1 pre-scan cost**: pass 1 today walks each macro body once.
  Pre-scan adds a second walk. Roughly 2× pass 1 body work for
  macro-heavy code. Accepted as the price of cleanliness.
- **Determinism is more load-bearing.** Today, divergence between
  passes corrupts FWDREF_LIST. After this change, it also corrupts
  macro-local resolution. Worth a clear assertion at end-of-pass that
  pre-scan and real-walk agreed on PC trajectory and slot fill set.
- **"Defined-so-far" tracking lives in the frame** during real-walk.
  It's transient — does not need to survive the walk. Reset (zero)
  at start of real-walk.
- **Args evaluated during pre-scan** must see only state that's
  deterministic across passes. Outer-frame slots already filled by
  pre-scan are deterministic; this should not be a new constraint.

## Pre-requisite work (do first)

This work assumes the parameter activation-frame work is already in
place:

1. Merged file/scope stack — single downward stack with variable-size
   memory-source frames; `FS_POP_MEMORY_HOOK` deleted.
2. Parameters stored in slot table on the merged stack frame, keyed
   by index into the macro def's name list. `LABEL_TYPE_MACRO`
   removed from LHASHTAB.
3. `prev_macro_frame` chain pointer through memory-source frames for
   recursion check and innermost-first lookup.
4. `EXPANSION_ID16` may still be alive at this point (still used by
   macro-locals); this work removes its last user.

**Status (as of source-stack unification Phase 4 completion):**
items 1–3 are done. The merged source stack lives in `source_stack.asm`
with a 1-byte `frame_size` at offset 0, the per-pop vtable replaced
`FS_POP_MEMORY_HOOK`, and `expand_macro` now pushes a single memory
frame whose payload carries `arg_count`, parameter slots
(`fwdref/value_L/value_H` per slot), and the scope block. Identifier
lookup in `resolve_identifier` consults the innermost macro frame's
slots via `ss_top_memory_frame` + `ss_lookup_param_slot` before
falling through to LHASHTAB; `LABEL_TYPE_MACRO` is gone.
`check_macro_recursion` walks the chain via
`ss_walk_frames_by_type`. Item 4 still applies — `EXPANSION_ID16`
remains for macro-locals and is the last user this work would remove.

## Order of attack when we come back

1. At `.macro` definition time, pre-scan the body to collect the
   list of macro-local label names; append them to the macro
   definition heap entry, after the parameter names.
2. Extend the activation frame slot table to include macro-local
   slots (sized by `arg_count + local_count`).
3. Implement pre-scan as a body walk that advances PC and fills
   macro-local slots, with the "assume ABS for unknown" rule.
4. Switch macro expansion to pre-scan + real-walk. Initially keep
   pre-scan-then-pop-then-real-walk semantics for nested invocations
   (simpler, exponential cost — fine for testing).
5. Switch to push-and-keep semantics for nested pre-scan (the 2×-flat
   cost design).
6. Remove `LABEL_TYPE_MACRO_LOCAL` and `EXPANSION_ID16`.
7. Verify FWDREF_LIST no longer receives entries for in-body
   macro-local refs (instrument and assert).

## Net conceptual outcome

A macro expansion becomes a self-contained unit of computation:
the frame is born, pre-scan fills it, real-walk consumes it, frame
dies. Nothing about the expansion outlives the expansion. The hash
holds globals and real-source local-under-global labels, full stop.
The macro system stops bleeding state into the rest of the assembler.
