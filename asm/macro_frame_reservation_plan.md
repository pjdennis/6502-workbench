# Plan: Reserve / commit split for macro source-stack frames

## Problem

`expand_macro` builds a memory frame whose payload is parsed argument
slots. The slots are written into the soon-to-be-frame's payload region
(at `SS_P16 - payload_size`) before the push, so we never need a
separate staging buffer. The push itself happens **after** argument
parsing.

Two complications fall out of that order:

1. The macro **name** lives in `TOKEN` (= `SS_NAME`) at entry, but
   `parse_expression` for a label-shaped argument calls `read_token`,
   which overwrites `TOKEN` with the label's name. By push time,
   `TOKEN` no longer holds the macro name. The current commit
   (`b2b18f9`) works around this by stashing `TOKEN` into a 128-byte
   `MACRO_NAME_SAVE` buffer at `$0480-$04FF` at entry, and restoring it
   just before `push_memory_source_reserve_payload`.
2. Argument parsing must happen with the **parent** frame on top of the
   source stack, so:
   - `read_char` keeps reading from the invocation site;
   - `CURR_LINE16` / `SS_SRC_TYPE` / the name at `(SS_P16)+5` all
     describe the parent — any error during arg parsing reports the
     invocation site, not "in macro &lt;new&gt; at line 1";
   - The new frame's `prev_data` (memory cursor) still captures
     parent's read position **after** argument bytes are consumed.

The save/restore workaround eliminates the symptom but leaves a
128-byte temporary buffer hanging around and obscures the underlying
shape of the operation: we want to **reserve** a frame, fill its pieces
in their natural locations, then **commit** atomically.

## Goal

Replace the `MACRO_NAME_SAVE` save/restore with a clean reserve/commit
split inside `source_stack.asm`. Keep stack mechanics generic;
`expand_macro` writes only the payload it owns.

## Design — two stack pointers

Two zero-page pointers describe the source stack:

- `SS_P16` — **committed** top. The frame at `SS_P16` is the current
  active source. This is what every existing consumer reads:
  `pop_source`, the prev_data path inside `pop_source`, the interrupt
  handler's location print, `show_include_traceback`,
  `ss_walk_frames`, `check_macro_recursion`'s starting point, etc.
  Semantics unchanged.
- `SS_PEND_P16` — **pending** top, i.e. the actual lowest extent of
  the stack including any in-flight reservation. Invariant:
  `SS_PEND_P16 <= SS_P16`, with equality whenever no reservation is
  in flight (which is the steady state outside `expand_macro`'s
  reserve→commit window).

A reservation **lowers `SS_PEND_P16` only**, leaving `SS_P16`
unchanged. The pending frame occupies `[SS_PEND_P16, SS_P16)`. While
that gap is non-empty:

- Every existing consumer still sees `SS_P16` as the top → the parent
  is the active source; reads, errors, and traceback walks all behave
  exactly as if `expand_macro` had not yet been entered.
- The heap-vs-stack OOM check uses `SS_PEND_P16`, not `SS_P16`, so the
  256-byte safety buffer is enforced against the **lowest stack
  extent** rather than the committed top. The pending region cannot
  collide with heap write-ahead.

Commit: `SS_P16 := SS_PEND_P16`. The pending frame becomes the
committed top in a single 16-bit copy. (Discard, if ever needed:
`SS_PEND_P16 := SS_P16` — the pending bytes simply revert to free
stack space.)

### Why two pointers (vs. relying on the safety buffer alone)

Earlier draft of this plan relied on the existing 256-byte safety
buffer to protect the pending region. That is unsafe. The buffer
guarantees `MEMP16 + 256 <= SS_P16`, which means heap write-ahead
via `(MEMP16),Y` reaches at most `SS_P16 - 1`. With the buffer at its
minimum and a pending frame of size `K`, the heap can write into the
pending region's top `K` bytes:

```
SS_P16 = $E000, MEMP16 = $DF00 (gap == 256, OOM check just barely passes)
Pending region (K=200): [$DF38, $DFFF]
Heap write-ahead: (MEMP16),Y at Y=$FF reaches $DFFF
                  -> collision at $DF38..$DFFF
```

Even though `parse_expression` doesn't grow the heap today, nothing
structural prevents a future change from doing so. A documented "don't
grow the heap during a reservation" rule is a latent bug waiting to
land.

The two-pointer scheme makes the protection structural: the same OOM
machinery that fences the heap off from the committed stack now fences
it off from the pending region too. No documentation-only invariant.

### Why two pointers (vs. advance `SS_P16` + `INCOMPLETE` marker)

The original suggestion was to advance `SS_P16` on reservation and
mark the new top frame `curr_type = INCOMPLETE` so consumers can skip
it. That works but pays in three places:

- `pop_source` must skip incomplete frames (otherwise `read_char`'s
  source-exhaustion path operates on the wrong frame).
- The interrupt handler (or a dedicated `ss_drop_incomplete` helper)
  must run before reading `(SS_P16)+5` for the error-location name.
- The vtable indexed by `curr_type` grows a third entry (or
  `pop_source` needs a pre-check before dispatch).

The two-pointer design moves all of that complexity into one place
(the SS_P16 / SS_PEND_P16 distinction inside source_stack.asm) and
needs **zero** changes to consumers — they all read `SS_P16` and
`SS_P16` continues to point at the committed top. The new
`SS_PEND_P16` only matters to `source_stack.asm` itself (push, pop,
reserve, commit) and to the OOM check.

## Pointer maintenance summary

| Operation | `SS_P16` | `SS_PEND_P16` |
|---|---|---|
| `source_stack_init` | `:= SOURCE_STACK` | `:= SOURCE_STACK` |
| Atomic push (file, plain memory) | decrements by frame_size | decrements by frame_size (lockstep) |
| Atomic pop (`ss_free_frame`) | increments by frame_size | follows `SS_P16` |
| Reserve | unchanged | decrements by frame_size |
| Commit | `:= SS_PEND_P16` | unchanged |
| Discard reservation (if ever needed) | unchanged | `:= SS_P16` |

Invariant `SS_PEND_P16 <= SS_P16` always holds.

Pops are only valid when `SS_PEND_P16 == SS_P16` (no reservation in
flight). In the assembler today this is guaranteed by usage —
`pop_source` is never called between `expand_macro`'s reserve and
commit. Worth an `enable_debug` assertion at the head of
`pop_source` / `ss_free_frame` if cheap.

## OOM check change

`common.asm:143` (`advance_heap`) currently calls
`CHECK_FOR_OUT_OF_MEMORY SS_P16`. Change to
`CHECK_FOR_OUT_OF_MEMORY SS_PEND_P16`.

`source_stack.asm:124` (`check_source_frame_room`) currently calls
`CHECK_FOR_OUT_OF_MEMORY SS_TEMP16` after computing
`SS_TEMP16 = SS_P16 - frame_size`. For atomic pushes that stays
correct (atomic pushes happen when `SS_P16 == SS_PEND_P16`). For
reserves the helper computes `SS_TEMP16 = SS_PEND_P16 - frame_size`
instead. Either way, `SS_TEMP16` ends up holding the proposed new
lowest extent, which is exactly what the OOM check wants.

## Frame layout: prev_data moves before the name

The current frame layout (`source_stack.asm:11-45`) places `prev_data`
**after** the variable-length name:

```
0:    frame_size
1:    curr_type
2:    prev_type
3-4:  prev_line_L, prev_line_H
5..(5+name_len): name + null
(after name):    prev_data (1 byte file / 2 bytes memory)
(after that):    payload
```

A prior reorg moved `curr_type / prev_type / prev_line` to fixed
offsets 1..4 so consumers wouldn't pay an O(name_len) scan on every
read. `prev_data` was left after the name because it's read only once
per pop. Nothing structural keeps it there — the prior reorg simply
didn't need to move it.

For the reserve/commit split, the variable position of `prev_data`
forces commit to either re-walk the name on every commit or remember
the offset across the reservation window. The first costs ~5
cycles/byte on a hot path (~40 cycles for an 8-character name); the
second costs a zp byte that's meaningful only between reserve and
commit and clutters the API.

A small reorder eliminates the choice. New layout:

```
0:    frame_size
1:    curr_type
2:    prev_type
3-4:  prev_line_L, prev_line_H
5-6:  prev_data           <-- moved here, FIXED 2-byte slot
7..:  name + null
...:  payload
```

`prev_data` becomes a **fixed 2-byte slot at offsets 5..6**, regardless
of `prev_type`. For `prev_type=file` only byte 5 is used; byte 6 is
unused (1 byte/frame waste for file parents).

### What this enables

- **`ss_commit_pending_frame` writes prev_data at constant offsets
  5..6**, with no zp-byte handoff from reserve. The proposed
  `SS_PEND_PREV_OFF` variable disappears entirely.
- **`pop_source`'s `.skip_name` loop disappears**
  (`source_stack.asm:445-448`). Today every pop walks the name once
  to find prev_data; with prev_data at offset 5 that walk is gone.
  Independent speedup for every pop, not just macro pops.
- **`push_source_frame`'s prev_data write moves to a fixed offset**
  (no name copy has to precede it). The 1-byte vs. 2-byte branch on
  `prev_type` stays — only the *position* becomes constant.
- **`check_source_frame_room` loses its parent-type branch.** Today's
  `5 + 1 + 1` vs. `5 + 2 + 1` (`source_stack.asm:103/108`) collapses
  to a single `5 + 2 + 1` since `prev_data` is always 2 bytes. The
  `SS_SRC_TYPE` read disappears from the size computation.
- **`expand_macro`'s "worst-case 15" comment becomes "constant 15"**
  (`macro_expansion.asm:278-281`). The frame size formula no longer
  depends on parent type.

### What this costs

- **Name moves from offset 5 to offset 7.** One consumer cares:
  `SHOW_FRAME_NAME` in `errors.asm:235-239` (used at `:294` and
  `:395`). One-line constant change: `ADCI16 ptr, $05, TABP16` →
  `ADCI16 ptr, $07, TABP16`. Plus the surrounding comment.
- **1 byte/frame wasted for file-parent frames.** Worst case in a
  typical compile is well under 50 bytes total — trivial against the
  128-byte `MACRO_NAME_SAVE` reclamation. The waste is transient
  stack usage during the file frame's lifetime; freed on pop.

### What stays unchanged

- `pop_label_scope_from_frame` (`label_scope.asm:98-119`) anchors at
  `frame_size - 7` (scope_block start, working backwards from the
  end of the frame). Name moving from offset 5 to 7 doesn't touch
  the end-of-frame layout, so this anchor is unaffected.
- `check_macro_recursion` (`macro_expansion.asm:38-84`) anchors at
  `frame_size - 2` (MACRO_ENTRY16). Same reasoning — unchanged.
- `ss_lookup_param_slot` (`macro_expansion.asm:110-208`) anchors at
  `frame_size - 7` for the scope_block. Unchanged.
- `MACRO_PAYLOAD_BASE16 = SS_P16 - payload_size`
  (`macro_expansion.asm:326-332`) — unchanged. Payload still trails
  the name; only the name's offset within the frame changed, not the
  payload's offset from the frame's end.

### Variants considered and rejected

- **A': variable-size `prev_data` at offset 5, name at offset 6 or
  7.** Saves the 1-byte/file-frame waste, but `SHOW_FRAME_NAME` has
  to read `prev_type` at offset 2 to compute the name offset. Net
  code growth probably exceeds the byte savings, and you lose the
  `check_source_frame_room` simplification.
- **B: `prev_data` at the end of the frame** (after payload). Also
  eliminates the per-commit offset problem and keeps name at offset
  5. But three end-of-frame anchors (`pop_label_scope_from_frame`,
  `check_macro_recursion`, `ss_lookup_param_slot`) all use
  `frame_size - K` and would each need a `prev_data_size`
  adjustment. Three call sites disturbed instead of one. Worse
  trade.

## New `source_stack.asm` API

Two public primitives plus an internal helper. All three are
record-type-agnostic — they manipulate the frame's stack-defined header
fields only. Payload semantics stay with the caller (today,
`expand_macro`).

### New zero-page state

```
SS_PEND_P16:           .word
; Pending top of the source stack. Equal to SS_P16 outside a
; reserve/commit window; less than SS_P16 (lower address, since stack
; grows down) when a frame is reserved but not yet committed. The
; heap-vs-stack OOM check is performed against this pointer, so the
; pending region is structurally protected from heap write-ahead.
```

Net zero-page delta: +2 bytes (one word). With the frame layout
reorder, `prev_data` sits at fixed offsets 5..6, so commit no longer
needs an offset hand-off from reserve. Clear net memory win once
`MACRO_NAME_SAVE`'s 128 bytes go away.

### Public primitives

```
ss_reserve_frame:
; Reserve a pending frame. SS_P16 does NOT advance -- only SS_PEND_P16
; does. The frame's header fields (frame_size at offset 0, curr_type
; at 1, prev_type at 2, prev_line at 3..4, name at 7..) are written
; into the pending region at SS_PEND_P16. Offsets 5..6 (the prev_data
; slot) are left UNINITIALIZED -- the parent's read cursor
; (SS_MEM_PTR16 in particular) typically advances during the reserved
; window, so the canonical prev_data is captured at commit time, not
; here.
;
; Until commit, parent's source remains active for read_char and
; visible to all stack consumers. Tracebacks for errors during the
; reserved window report parent's location.
;
; OOM is checked here against SS_PEND_P16 - frame_size, so the pending
; region is structurally protected from heap collision. On OOM the
; routine jumps to err_out_of_memory with no state to roll back
; (SS_PEND_P16 hasn't moved yet at the point of check).
;
; On entry: A             = curr_type for the new frame
;           SS_NAME       = new frame's name (null-terminated)
;           SS_SRC_TYPE / SS_CURR_LINE16 / SS_CURR_FILE / SS_MEM_PTR16
;                         = parent's state (consumed for prev_type and
;                           prev_line; prev_data deferred to commit)
;           SS_PAYLOAD_SIZE = trailing payload bytes to reserve
; On exit:  SS_PEND_P16   = pending frame base
;           SS_PAYLOAD_SIZE reset to 0
;           SS_P16 unchanged. SS_SRC_TYPE / SS_CURR_LINE16 /
;             SS_CURR_FILE / SS_MEM_PTR16 unchanged (parent still active)
;           A, X, Y clobbered. Caller saves X if needed.

ss_commit_pending_frame:
; Commit a pending frame:
;   1. Write prev_data at fixed offsets 5..6 within the pending
;      frame, using the CURRENT SS_CURR_FILE (file parent: 1 byte at
;      offset 5; offset 6 unused) or SS_MEM_PTR16 (memory parent:
;      lo at 5, hi at 6). prev_type at offset 2 selects which.
;      This captures parent's read cursor at the moment the new
;      source takes over.
;   2. Advance SS_P16 := SS_PEND_P16 (the pending frame becomes the
;      committed top).
;   3. Set SS_SRC_TYPE := the frame's curr_type byte at offset 1.
;   4. Reset SS_CURR_LINE16 := 0.
;
; Caller is still responsible for installing SS_MEM_PTR16 (memory
; frames -- macro body pointer) or SS_CURR_FILE (file frames -- new
; handle), since the source-stack module doesn't know what those
; should be.
;
; A, Y clobbered. X preserved.
```

### Internal sharing

`push_source_frame` (today the inner workhorse for `push_file_source`
and `push_memory_source_reserve_payload`) writes the full frame
atomically. With prev_data at fixed offsets 5..6, the natural split
between reserve and commit is:

- **header (offsets 0..4) + name (offsets 7..)** (reserve)
- **prev_data (offsets 5..6)** (commit)

The header + name writes are identical between the atomic
`push_source_frame` path and the new `ss_reserve_frame`. A clean
factoring is to extract `ss_write_pending_header_and_name` as an
internal helper used by both:

- `push_source_frame` (atomic) calls the helper, then writes prev_data
  inline at fixed offsets 5..6 using the parent's current state, then
  resets `SS_CURR_LINE16`.
- `ss_reserve_frame` calls the helper and returns; the prev_data
  write at offsets 5..6 is deferred to `ss_commit_pending_frame`.

No offset hand-off is needed — both writers know prev_data lives at
offset 5 (and 6 for memory parents).

### Why prev_data is deferred to commit, not written by reserve

`SS_MEM_PTR16` advances during arg parsing (every char read of a
memory parent increments it). `SS_CURR_LINE16` doesn't change in
practice (args don't span lines), but for memory parents the
**cursor** does. To capture parent's "next read position after the
invocation," we have to write `prev_data` after arg parsing finishes,
i.e. at commit.

Reserve still writes `prev_type` at offset 2 (parent's `SS_SRC_TYPE`,
stable during the reserved window because no push/pop happens), so
commit knows whether to write 1 byte (file) or 2 bytes (memory) of
prev_data without re-checking parent state. The position is fixed
either way.

## `expand_macro` after the refactor

```
expand_macro:
  CP16 MACRO_DEF_PTR16, MACRO_ENTRY16
  JSR check_macro_recursion
  TXA
  PHA                             ; save output file handle (X)

  ; Read N from the def, advance MACRO_DEF_PTR16 past the count byte.
  ; ...same as today...

  ; Compute payload_size = 3*N + 7 -> SS_PAYLOAD_SIZE.
  ; ...same as today...

  ; Exact frame_size sanity check (1-byte field):
  ; 15 + name_len + 3*N <= 255, else jmp err_too_many_arguments.
  ; (With the layout reorder, prev_data is always 2 bytes, so 15 is
  ; exact rather than worst-case -- the file/memory branch in
  ; check_source_frame_room is gone.)

  ; Reserve the pending frame. ss_reserve_frame copies SS_NAME (=
  ; TOKEN, the macro name) into the pending frame's name region.
  ; After this, parse_expression / read_token may freely clobber
  ; TOKEN -- the captured name lives in the pending frame.
  LDA #SS_SRC_TYPE_MEMORY
  JSR ss_reserve_frame

  ; Compute payload base. SS_P16 hasn't moved, so MACRO_PAYLOAD_BASE16
  ; = SS_P16 - payload_size still works (same computation as today).
  ; (Equivalent to SS_PEND_P16 + frame_size - payload_size; the SS_P16
  ; form is shorter and matches the pre-refactor code.)
  ...

  LDX #0
.parse_loop:
  ; ...parse args, write slots into (MACRO_PAYLOAD_BASE16),X+Y...
  ; (Identical to today's body.)

.args_done_ok:
  ; Write scope_block tail into payload (offset 3*N..3*N+6).
  ; (Identical to today.)

  ; Switch to new label scope (allocate new EXPANSION_ID).
  ; (Identical to today.)

  ; Commit. ss_commit_pending_frame writes prev_data from current
  ; parent state (SS_MEM_PTR16 captured POST-arg-parse), advances
  ; SS_P16 := SS_PEND_P16, sets SS_SRC_TYPE := MEMORY, resets
  ; SS_CURR_LINE16.
  JSR ss_commit_pending_frame

  ; Anchor MACRO_LOOKUP_FRAME16 at the new top frame.
  LDA SS_P16
  STA MACRO_LOOKUP_FRAME16
  LDA SS_P16 + 1
  STA MACRO_LOOKUP_FRAME16 + 1

  ; Install body pointer.
  CP16 MACRO_DEF_PTR16, SS_MEM_PTR16

  PLA
  TAX
  RTS
.too_many:
  JMP err_too_many_arguments
```

Net delta inside `expand_macro`:

- **Removed**: `save_token` loop at entry, `restore_token` loop before
  push, `MACRO_NAME_SAVE` reference.
- **Removed**: standalone `JSR check_source_frame_room` (folded into
  `ss_reserve_frame`).
- **Replaced**: `JSR push_memory_source_reserve_payload` →
  `JSR ss_commit_pending_frame`.
- **Removed**: the `SS_SRC_TYPE := MEMORY` and `LDA #0; STA
  SS_PAYLOAD_SIZE` writes that today live in
  `push_memory_source_reserve_payload` — they're inside the new
  reserve / commit pair.

Everything else (slot-write loop, scope_block tail, scope switch,
`MACRO_LOOKUP_FRAME16` anchor, body pointer install) is unchanged.

## OOM handling

The two-pointer design keeps OOM trivially clean:

- `ss_reserve_frame` calls `check_source_frame_room` with
  `SS_TEMP16 = SS_PEND_P16 - frame_size` and the OOM check compares
  that against `MEMP16`. If the check jumps to `err_out_of_memory`,
  no state has changed: neither `SS_P16` nor `SS_PEND_P16` has moved,
  no pending bytes written, no resources acquired. Traceback walks
  parent + ancestors normally.
- After a successful reserve, the pending region is structurally
  protected from heap collision (the heap's `advance_heap` uses
  `SS_PEND_P16` for its OOM check, so any heap growth attempt that
  would hit the pending region fails immediately with
  `err_out_of_memory`).
- If commit doesn't run (caller errors out between reserve and commit
  for any reason — e.g., `parse_expression` raises
  `err_label_not_found` on a malformed arg), the pending bytes are
  unreachable from any consumer (because they read `SS_P16`).
  `SS_PEND_P16 < SS_P16` will remain that way until the program
  exits, but that's fine — errors here are terminal. (If we ever
  have a recoverable error mode, `SS_PEND_P16 := SS_P16` cleans up
  in one instruction.)

## Memory map cleanup

`MACRO_NAME_SAVE` at `$0480-$04FF` (128 bytes) becomes free once
`expand_macro` no longer references it. The `$0400-$04FF` region
returns fully to the "free" state documented in `asm.asm` after Phase
3.6. Update the comment block in `asm.asm` and the memory-map section
in `CLAUDE.md`.

Net memory: -128 bytes buffer + 2 bytes zp (`SS_PEND_P16` word) =
-126 bytes overall. The frame layout reorder also adds 1 byte/frame
of transient stack waste for file-parent frames (typically <50 bytes
across all frames in flight; freed on pop), which doesn't affect the
overall budget meaningfully.

## Test coverage

Existing tests that must stay green:

- `macro_error_traceback_with_identifier_arg`
  (`15-macros_advanced.txt:262`) — the regression test that pinned
  down the `TOKEN`-clobbering bug. Should pass without
  `MACRO_NAME_SAVE` because reserve writes the name before
  `parse_expression` runs. The test description (line 263) actually
  describes the **target** behavior of this plan, not the current
  workaround — fixing it that way will make the test description
  accurate for the first time.
- `macro_nesting_overflow` (`18-memory_limits.txt:142`) — OOM at the
  source-stack push boundary. `ss_reserve_frame`'s OOM check must
  produce the same traceback.
- All `oom_*` tests in `source_stack_tests.txt:660+` — push-time OOM
  via injected `OOM_LIMIT16`.
- The four scope-invariant tests (Phase 4.1) — shadowing,
  non-leakage, visibility through `.include`, non-leakage through
  `.include`.
- `macro_args_at_cap` — 64 args fit; frame_size sanity check still
  works.

New tests to add:

- **Heap-vs-pending collision is structurally blocked.** The most
  important new test, since the whole two-pointer scheme exists to
  make this safe. Source-stack component test program: synthetic
  scenario where `ss_reserve_frame` is called and then the test
  attempts a large heap allocation that would fit if the OOM check
  used `SS_P16` but does not fit when it uses `SS_PEND_P16`. The
  allocation must fail with `err_out_of_memory`. Today this can't
  trigger (no caller). After the change, it must.
- **OOM during `ss_reserve_frame` doesn't leak a half-built frame.**
  Drive the source stack near `OOM_LIMIT16`, then attempt a macro
  invocation whose worst-case frame would push past the limit.
  Assert `err_out_of_memory` fires and that `SS_P16` and
  `SS_PEND_P16` are both at parent's value (no orphan frame, no
  divergent pointers). Best done in the source-stack component test
  program with a synthetic equivalent of "reserve a pending frame
  near the limit" exposed via a new `@reserve_then_commit` directive.
- **Pending region invisible to consumers.** Source-stack test
  program: a new `@reserve_only` directive reserves a frame and
  returns without committing. `@frames` / `@info` then must report
  the same shape as before the reserve (since SS_P16 didn't move).
  Pins down "consumers see only committed frames."
- **Successful reserve→commit produces a frame indistinguishable
  from an atomic push.** Source-stack test program: do an atomic
  `push_memory_source_reserve_payload`-equivalent and a
  reserve→commit-equivalent, both with the same name and payload
  bytes, then walk both via `@frames`. Outputs must match. Pins down
  "the new path produces correct frames."
- **Explicit-line-number variant of
  `macro_error_traceback_with_identifier_arg`** that asserts the
  parent's line number, not just the name. Pin down that the line
  reported on arg-parse error is the invocation line, not "line 1
  of the macro."
- **Layout-reorder pin.** Source-stack component test program: a
  `@layout_check` directive that pushes a frame with known name and
  prev_data, then asserts (via `@info`) that the name appears at
  offset 7 and the prev_data byte(s) appear at offsets 5..6. Catches
  any future reorg that accidentally reverts the layout. Should also
  verify SHOW_FRAME_NAME's output is correct (i.e., that the offset
  constant in the macro was updated).

## Phasing

Per the project's small-commits TDD workflow:

1. **Reorder the frame layout: prev_data slot to offsets 5..6, name
   to offset 7.** Update `push_source_frame` (write prev_data at
   fixed offset 5..6 instead of after name copy), `pop_source` (drop
   the `.skip_name` loop, read prev_data at offset 5 directly),
   `check_source_frame_room` (single `5 + 2 + 1` formula, drop the
   parent-type branch), and `SHOW_FRAME_NAME` in `errors.asm`
   (`$05` → `$07`). Update the layout comment block at the top of
   `source_stack.asm`. Add the layout-reorder pin test. Self-host
   verifies. Commit.
2. **Add `SS_PEND_P16` zp word**, initialize in `source_stack_init`,
   maintain in `ss_alloc_frame` / `ss_free_frame`. Switch
   `advance_heap`'s `CHECK_FOR_OUT_OF_MEMORY` from `SS_P16` to
   `SS_PEND_P16`. No behavior change yet (since `SS_PEND_P16 ==
   SS_P16` always at this stage). Full chain green. Commit.
3. **Refactor** — extract `ss_write_pending_header_and_name`
   internal helper from today's `push_source_frame`, writing
   header (offsets 0..4) and name (offsets 7..). prev_data write
   stays inline in `push_source_frame`. Behavior unchanged. Full
   chain green. Commit.
4. **Add the heap-vs-pending collision test, the OOM-during-reserve
   test, and the pending-region-invisible test** in the source-stack
   suite. Add new directives `@reserve_then_commit` and
   `@reserve_only` exposing the new primitives. Initial state:
   primitives don't exist yet, tests fail. Commit (red).
5. **Add `ss_reserve_frame` / `ss_commit_pending_frame` primitives.**
   `ss_commit_pending_frame` writes prev_data at fixed offsets 5..6
   directly. Tests from step 4 pass. Commit (green).
6. **Migrate `expand_macro`.** Replace the save/restore + payload
   pre-write + push sequence with reserve + payload write + commit.
   Drop the `MACRO_NAME_SAVE` reference from `macro_expansion.asm`.
   `15-macros_advanced.txt:262` and the four scope-invariant tests
   stay green; `oom_*`, `macro_nesting_overflow`, and
   `macro_args_at_cap` stay green. Self-host verifies. Commit.
7. **Add the explicit-line-number variant of
   `macro_error_traceback_with_identifier_arg`** that asserts the
   parent's line number, not just the name. Commit.
8. **Reclaim `MACRO_NAME_SAVE`.** Remove the equate from `asm.asm`
   and update the surrounding comment block. Update `CLAUDE.md`'s
   memory map. Drop `push_memory_source_reserve_payload` if
   `expand_macro` was its only caller (likely true). Commit.
9. **Optional: drop or rename the leftover atomic push helpers.**
   `push_file_source` could be re-implemented as
   `ss_reserve_frame` + immediate commit + handle install for
   symmetry. Skip this if it costs more than it saves; the existing
   atomic path is fine for non-macro pushes.

Each commit: build via `./asmtestgen.sh`, run `python3 run_tests.py
-q`, and (if `source_stack.asm` is touched) the source-stack
component suite. No editor work touches this plan.

Step 1 (the layout reorder) is independent of the reserve/commit
work and could ship on its own; landing it first gives the
reserve/commit primitives in steps 4–5 a fixed-offset world to
target. If step 1 reveals an unexpected dependency on the old
layout, the rest of the plan still works against the old layout —
revert step 1 and reintroduce a `SS_PEND_PREV_OFF` zp byte for
commit (the variant the plan was originally drafted around).

## Risks and watchouts

- **Pointer maintenance discipline.** Every push and pop must update
  both pointers in lockstep when `SS_P16 == SS_PEND_P16` (the steady
  state). The split-step pattern (reserve → … → commit) is the only
  exception. Centralizing this in `ss_alloc_frame` /
  `ss_free_frame` makes it hard to get wrong; ad-hoc pointer
  manipulation outside those routines is a smell. Worth an
  `enable_debug` assertion in `pop_source` / `ss_free_frame` that
  `SS_PEND_P16 == SS_P16` on entry — pop while a reservation is
  pending would silently corrupt the stack.
- **Order of operations inside `ss_reserve_frame`.** The OOM check
  must come before any writes; the writes must use the **pending**
  base (computed from `SS_PEND_P16 - frame_size`, stored back into
  `SS_PEND_P16` after the OOM check passes), not `SS_P16`. Mixing
  the two would silently overwrite the parent's frame. Mitigated by
  the new pending-region-invisible test.
- **`SS_PAYLOAD_SIZE` lifecycle.** Today
  `push_memory_source_reserve_payload` resets it to 0 on success.
  `ss_reserve_frame` should keep that invariant so subsequent pushes
  default to no-payload.
- **Frame-layout offset constants.** With `prev_data` at fixed
  offsets 5..6 and the name at offset 7, three constants change
  meaning: `5` (was name start, now prev_data start), `7` (new name
  start), and the `5 + N + 1` frame-size formula collapses to
  `5 + 2 + 1`. Audit every literal `#5` / `#$05` / `+ 5` in
  `source_stack.asm`, `errors.asm`, and any nearby helpers during
  step 1 to ensure none is silently relying on the old name offset.
  The layout comment block at `source_stack.asm:11-45` is the
  canonical reference and must be updated in lockstep.
- **File-parent prev_data byte 6 is unused, not zero.**
  `push_source_frame` writes prev_data byte 5 (the file handle) for
  file parents, but doesn't touch byte 6. Don't write code that
  reads offset 6 expecting `$00`; only `pop_source`'s prev_type
  branch (which reads byte 5 only for file parents) is correct.
- **`prev_data` capture timing.** Reserving prev_data eagerly would
  capture parent's `SS_MEM_PTR16` **before** arg parsing consumes
  bytes from it, so on eventual pop the parent would re-read those
  bytes. Commit-time capture matches today's behavior; the plan is
  explicit about this so a future tweaker doesn't move the write
  earlier "for symmetry."
- **Debug-build assertion vs. release-build silence.** The
  `SS_PEND_P16 == SS_P16` invariant on pop is something we want
  enforced cheaply; `enable_debug` is the existing knob. If a future
  failure mode needs the assertion in release too, escalating it is
  a separate decision.
