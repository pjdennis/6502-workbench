# Plan: Unify Scope Stack with File Stack, then Move Macro Parameters to Activation Frames

This is the implementation plan for two related changes:

1. Merge the scope stack (`SCOPE_STACK` at `$0400`) into the file stack
   (downward stack at `$F000`), and rename the merged stack to better
   reflect its multiple roles.
2. Move macro parameter storage out of `LHASHTAB` into per-invocation
   activation records carried on the merged stack.

Both align with the design discussion captured in
`macro_local_design_notes.md` (which is **deferred** — do not pull
macro-local label work into this plan).

## Working principles

- Red/green TDD: failing test first, then implementation, then commit.
- Small commits — one increment per commit, story-of-the-work history.
- Refactor before changing behavior, refactor again after, both committed
  separately.
- After every commit: `./asmtestgen.sh` (full self-host verification) +
  `python3 run_tests.py -q` + `python3 editor/tests/editor_tests.py -q`
  (last only if editor touched, which it shouldn't be).
- The source_stack component test suite (`17/tests/source_stack/`,
  formerly `17/tests/file_stack/`) is the primary verification
  surface for the stack refactors. Extend it early and lean on it.
- Use `./commit -m"..."` not `git commit`.

## Naming

Rename `file_stack` → `source_stack` throughout. Rationale:

- It's already a stack of input sources (file or memory), not just files.
- It will gain activation-record duties (scope, parameters, eventually
  macro-locals).
- "Source" stays accurate after every planned addition.

Symbol renames:

- `file_stack.asm` → `source_stack.asm`
- `FS_*` zero-page vars → `SS_*` (e.g. `FS_P16` → `SS_P16`,
  `FS_CURR_CHAR` → `SS_CURR_CHAR`, `FS_MEM_PTR16` → `SS_MEM_PTR16`)
- `file_stack_init` → `source_stack_init`, etc.
- `FILE_STACK` (the address constant) → `SOURCE_STACK`
- `FS_FILENAME` → `SS_NAME` (it's a buffer for the source's name, not
  necessarily a filename for memory sources)
- `FS_POP_MEMORY_HOOK` → goes away in Phase 3 anyway, but is renamed in
  Phase 1 to `SS_POP_MEMORY_HOOK` for symmetry during the transition

The component test program also gets renamed (`file_stack_test.asm`,
`file_stack_tests.txt`, the test directory). Update `run_tests.py` /
test runner references.

## Abstraction goal

Today, `source_stack.asm` mixes three concerns:

1. **Stack mechanics**: bounds check, advance pointer, copy bytes in/out
   relative to `SS_P16`.
2. **Frame layout knowledge**: where the name is, where `curr_type`
   lives, which prev-data variant follows.
3. **Per-frame-type behavior**: open/close a file, manage a memory
   pointer, run the (current) `SS_POP_MEMORY_HOOK`.

The refactor target: stack mechanics generic, frame walking driven by a
size-byte at a fixed offset, per-type behavior dispatched from a small
table on `curr_type`.

### Two source types, not three

Earlier drafts of this plan introduced a third `curr_type=macro` for
activation frames. That distinction is unnecessary. In the real
assembler `push_memory_source` is called from exactly one place
(`expand_macro`), and the test program's `@memory` directive is just
a fixture for the same machinery. So we keep two types:

- **file** — read via `read` syscall on `SS_CURR_FILE`.
- **memory** — read via `LDA (SS_MEM_PTR16)`. May carry an optional
  trailing **payload** region whose interpretation belongs to the code
  that pushed the frame (Phase 3 puts scope/macro-entry there; Phase 4
  appends parameter slots). The source stack itself never reads the
  payload.

"Macro-ness" lives entirely in (a) who installs the payload bytes at
push time, and (b) who consumes them via the configured pop hook. The
test program pushes memory frames with no payload; the assembler
pushes memory frames with payload. Neither needs a distinct type tag.

### Tentative unified frame layout

```
[0]      frame_size               size in bytes of this frame
[1]      curr_type                0=file, 1=memory
[2]      prev_type
[3..4]   prev_line_L / prev_line_H
[5..]    type-specific payload    (name\0 first, then prev_data, then
                                   any caller-supplied payload bytes)
```

`frame_size` at offset 0 makes both push (set up size, fill payload)
and pop (read size, advance pointer) trivial. Frame walking from
`SS_P16` to top of stack iterates by adding `frame_size` each step.
Memory frames with payload have a larger `frame_size` than plain
memory frames; nothing else differs.

Generic helpers:

- `ss_push_frame_of_size A` — bounds check, allocate, set offset 0.
- `ss_pop_frame` — read size, dispatch on `curr_type`, deallocate.
- `ss_walk_frames callback_addr` — call callback for each frame from
  newest to oldest with frame ptr in TABP16 and Y free.
- `ss_walk_frames_by_type type, callback_addr` — same, filtered by
  `curr_type`. Sole assembler-side consumer is Phase 3.3's
  `check_macro_recursion`, which has to visit *every* memory frame
  looking for one whose macro identity matches.
- `ss_top_memory_frame` (Phase 4) — return a pointer to the innermost
  memory frame, or signal "none". Phase 4's parameter lookup is a
  single-frame access, but it must **skip past any file frames** on
  top — `.include` from inside a macro pushes a file frame above the
  macro's memory frame, and asm17 today still resolves the macro's
  params from inside that included file. (Sketch only — add when 4.6
  lands.)

Per-type vtable (two entries, indexed by `curr_type`):

- file → `close()` then standard prev_data restore.
- memory → run `SS_POP_MEMORY_HOOK` if defined (consumes payload),
  then standard prev_data restore.

## Phase 0 — Shore up file_stack test coverage

**Goal**: confidence that subsequent refactors don't regress
push/pop/walk behavior, and a place to anchor new behaviors.

Audit the existing 31 tests; identify gaps. Likely gaps:

- Push/pop balance assertions (does `SS_P16` return exactly to
  `SOURCE_STACK` after all sources unwind across various nestings?).
- Frame size correctness for variable-length names.
- Frame iteration in any direction (no current external API to
  inspect the stack — adding one helps later phases too).
- Out-of-memory path on push (the test program currently stubs the
  `CHECK_FOR_OUT_OF_MEMORY` macro to no-op — replace with a controlled
  failure indicator the test can observe).

Tasks (each its own commit):

- **0.1** Add a `frames` mode to the test program that prints the
  current frame chain (depth, type, name). Exercise it with simple
  cases. Failing tests first → implement mode → green.
- **0.2** Add tests that assert push/pop balance using the new mode
  combined with `info` mode (compare `SS_P16` before/after).
- **0.3** Add an OOM injection test mode: configurable
  `CHECK_FOR_OUT_OF_MEMORY` that errors via the test runner so
  exhaustion is observable. Add a test that pushes until OOM and
  verifies cleanup.
- **0.4** Add a test that exercises a memory source with a forward-
  looking "extra payload" attached to the frame, accessible via the
  `frames` mode. This is the seed for Phase 3's activation data —
  prove the test infra can see it before we use it.

Stop. Commit. Verify.

## Phase 1 — Rename file_stack → source_stack

Pure mechanical refactor. No behavior change.

Tasks:

- **1.1** Rename file `file_stack.asm` → `source_stack.asm`. Update
  `asm.asm` include line and `file_stack_test.asm` include line. Run
  full chain + tests.
- **1.2** Rename `FILE_STACK` constant → `SOURCE_STACK`. Update both
  consumers (`asm.asm`, `file_stack_test.asm`).
- **1.3** Rename `FS_*` zero-page vars → `SS_*`. Single commit, full
  sweep. Includes `FS_P16`, `FS_CURR_CHAR`, `FS_CURR_LINE16`,
  `FS_CURR_FILE`, `FS_MEM_PTR16`, `FS_SRC_TYPE`, `FS_TEMP16`.
- **1.4** Rename `FS_*` constants and routines → `SS_*` /
  `source_stack_*`. Includes `FS_FILENAME`, `FS_SRC_TYPE_FILE/MEMORY`,
  `FS_POP_MEMORY_HOOK`, `FS_ERR_NO_FILE`, `file_stack_init`,
  `file_stack_empty`, `push_file_stack`, `push_memory_source`,
  `pop_source` aliases, `file_stack_read_char`.
- **1.5** Rename test artifacts: `file_stack_test.asm`,
  `file_stack_tests.txt`, test directory, `run_tests.py` references.

Each commit: name change only, full chain green.

## Phase 1.6 — Pre-Phase-2 cleanup

Three small docs/cleanup commits that are still in the spirit of "no
behavior change," to land before the Phase 2 abstraction work begins.
None of these need new tests; existing tests prove they're inert.

- **1.6.1** Fix the `push_memory_source` API contract. The current
  comment says
  ```
  ; On entry: SS_NAME = name for this memory source
  ;           SS_MEM_PTR16 = start of zero-terminated memory buffer
  ```
  which is misleading and is what caused the
  `setup_memory_source` bug found in Phase 0.4. The actual contract
  is: at entry, `SS_MEM_PTR16` must still hold the **parent's** read
  position (so `push_source_frame` can save it as `prev_data` for a
  memory→memory push); the caller installs the new buffer pointer
  **after** `push_memory_source` returns. Document this clearly and
  add a one-liner reminder above the call site in
  `macro_expansion.asm`.
- **1.6.2** Tighten the `source_stack.asm` module header: drop the
  "filename buffer" wording on `SS_NAME` (it's any source's name),
  reword the prev_data comment so the `(2 bytes, zero-terminated)`
  parenthetical doesn't read as describing the field's encoding, and
  fix the `pop_source` comment that still says `FS_MEM_PTR`.
- **1.6.3** Mark `push_source_frame` as internal in its leading
  comment — it's a building block called only by the two public push
  routines, not part of the source stack's public surface.

After 1.6, all of Phase 1's renames + cleanup are landed and the
module's public docs accurately describe the current behavior. Phase 2
can then refactor with no remaining ambiguity about how the API is
meant to be called.

## Phase 2 — Refactor for abstraction (no behavior change)

Goal: split stack mechanics from frame layout from per-type behavior.
Behavior identical at every commit.

Tasks:

- **2.1** Introduce `frame_size` byte at offset 0 of every frame.
  Adjust `push_source_frame` to set it; adjust `pop_source` to read
  it; adjust internal navigation. The `name` field shifts by 1 byte.
  Run full chain + source_stack tests + assembler tests.
- **2.2** Extract the generic stack mechanics (bounds check, allocate,
  deallocate by size) into `ss_alloc_frame` / `ss_free_frame`. The
  current push and pop call them.
- **2.3** Replace the inline `BNE .save_memory_state` pop dispatch
  with a tiny vtable: a 2-entry array of `on_pop` handler addresses
  indexed by `curr_type` (file=0, memory=1). `pop_source` reads
  `curr_type`, indirects through the table.
- **2.4** Add `ss_walk_frames` (generic) and `ss_walk_frames_by_type`
  (filtered) helpers using `frame_size`. Cover with unit tests via
  the `frames` mode added in Phase 0.
- **2.5** Remove the `SS_POP_MEMORY_HOOK` indirection in favor of the
  `on_pop` vtable. The macro `pop_label_scope` is still hooked, but
  through the vtable now. (Will be deleted in Phase 3.)

Each commit: full chain + source_stack tests green.

## Phase 3 — Merge scope stack into source stack

Goal: remove `SCOPE_STACK`, `SCOPE_PTR16`, `SCOPE_LIMIT`, the entire
`label_scope.asm` module's stack (the routines may stay during
transition, then go).

Memory frames stay `curr_type=memory`. The change is that some memory
frames now carry a trailing **payload** region holding the activation
state (LABEL_SCOPE16, CACHED_HASH, MACRO_ENTRY16, prev_macro_frame_L/H).
The pop-memory hook learns to consume this payload; the source stack
itself is unchanged.

Tasks:

- **3.1** **Test first.** Add source_stack tests that prove the
  merged layout: a memory frame pushed with extra payload bytes
  trailing the standard fields is allocated, walked, and popped with
  `frame_size` correctly accounting for the payload. The test
  program gets a `@payload_memory <hex>` directive that exercises
  this; `@frames` and `@top_frame_size` already report enough state
  to verify. These tests fail until 3.2 lands.
- **3.2** Extend `push_memory_source` (or add a thin wrapper) to
  accept a payload size and copy payload bytes into the frame
  immediately after the standard prev_data. `frame_size` (added in
  Phase 2) absorbs the larger size automatically — no API outside
  the push routine cares. The pop hook reads the same payload bytes.
- **3.3** **Test first.** Failing test for `check_macro_recursion`
  via chain walk (the current SCOPE_STACK walk path). Then rewrite
  `check_macro_recursion` to walk the `prev_macro_frame_L/H` chain
  threaded through memory-frame payloads, and delete the fixed-stride
  SCOPE_STACK loop in `macro_expansion.asm`.
- **3.4** Migrate `expand_macro` to call the extended
  `push_memory_source` with the activation payload, instead of
  `push_label_scope` + bare `push_memory_source` separately. Two
  pushes become one.
- **3.5** Migrate `pop_label_scope`'s logic into the memory-pop hook
  installed via `SS_POP_MEMORY_HOOK` (which Phase 2 has already
  routed through the per-type vtable). The hook reads the payload
  fields and restores `LABEL_SCOPE16`, `CACHED_HASH`, etc.
- **3.6** Delete `SCOPE_STACK`, `SCOPE_PTR16`, `SCOPE_DEPTH`,
  `SCOPE_LIMIT`, `SCOPE_ENTRY_SIZE`, `init_scope_stack`,
  `push_label_scope`, `pop_label_scope`. The `label_scope.asm` file
  shrinks dramatically or disappears (its remaining content — just
  the `SCOPE_DEPTH` accessor used by `read_local_label`'s "are we in
  a macro" check — moves to source_stack as `ss_in_macro_expansion`
  derived from chain head).
- **3.7** Delete the `MACRO_ENTRY16` zero-page var if it's now
  redundant with the activation-payload field.
- **3.8** Reclaim the `$0400-$04FF` region. Choose a use or document
  it free.
- **3.9** Replace the `err_macro_nesting_too_deep` error with the
  out-of-memory error path (which is what the source stack already
  uses for overflow). Update tests.

Commits per task. Full chain + all tests green at each.

## Phase 4 — Macro parameter activation frames

Goal: parameters live in slots on the macro frame, not in `LHASHTAB`.

Throughout this phase, "macro frame" is shorthand for a memory frame
whose payload carries macro activation state (the scope/macro-entry
fields added in Phase 3, plus the parameter slots added here). It is
not a separate `curr_type` — the source stack still sees only files
and memory.

Tasks:

- **4.1** Verify the parameter scoping invariants are pinned down.
  Tests covering all four cases below have already been added to
  `17/tests/asm/15-macros_advanced.txt` (passing under the current
  EXPANSION_ID-scoped hash); Phase 4 must keep them green.
    - *Shadowing* (`macro_inner_param_shadows_outer`): outer macro
      has `x`, inner has `x`, body of inner uses `x` — must resolve
      to inner.
    - *Non-leakage, direct* (`macro_outer_param_not_visible_in_inner`):
      outer macro has `y`, inner has only `z`, body of inner uses
      `y` — must NOT see outer's `y`.
    - *Visibility through `.include`* (`macro_param_visible_in_include`):
      macro `M` takes `x`, body does `.include foo.asm`, foo.asm
      references `x` — must resolve to `M`'s `x`. The included file
      is a file frame on top of `M`'s memory frame, but param lookup
      skips past the file frame to reach `M`.
    - *Non-leakage through `.include`*
      (`macro_outer_param_not_visible_via_include`): outer `B` takes
      `y`, calls inner `A` with `z`, `A`'s body does `.include
      foo.asm`, foo.asm references `y` — must NOT see `B`'s `y`.
      Lookup stops at the *innermost* memory frame.
- **4.2** **Test first.** Add a test that proves param hash entries
  do not leak. Today this fails (or is a no-op since we can't inspect
  the heap easily). Approach: a debug-mode assembler stat or a
  controllable heap-watermark check that asserts heap usage after a
  macro-heavy run is bounded by definition cost only. May require a
  small instrumentation hook.
- **4.3** Refactor identifier lookup to call out to a single
  `resolve_identifier` choke point that today goes straight to the
  hash. No behavior change yet. Commit.
- **4.4** Extend macro-frame layout with `arg_count` + `slots[N]`
  (3 bytes per slot: value_L, value_H, fwdref). `expand_macro`
  populates slots from `MACRO_ARG_BUF` directly into the frame
  instead of via `hash_add` / `store_hash_value`. Keep the hash path
  alive in parallel for now (write to both). Tests still green via
  hash. Commit.
- **4.5** **Test first.** Add a test that resolves a parameter from
  the innermost macro frame's slot when the hash entry is intentionally
  absent (instrument `expand_macro` with a flag to skip the hash
  write). Fails before lookup change.
- **4.6** Update `resolve_identifier` to look up parameters in the
  innermost macro frame before consulting the hash. The frame's
  `macro_def_ptr` points at the parameter name list in the macro
  definition; lookup linear-scans the names, uses the matched index
  to read the slot from the frame's payload. **No copying of names.**
  Add `ss_top_memory_frame` (a one-shot scan that returns the newest
  memory frame's address, or signals "none") and use it here.

  **Scoping note**: this preserves asm17's current parameter scoping
  semantics. Today, `expand_macro` hashes parameters under the
  current `EXPANSION_ID`, so an inner macro's body sees only its own
  parameters and falls through to globals — outer-macro parameters
  are not visible. Two consequences worth being explicit about:
    - Lookup is single-*memory-frame*: only the innermost macro's
      params resolve, then the hash takes over. Outer macros'
      parameters do not bleed in.
    - Lookup is source-type-agnostic: `.include` inside a macro
      pushes a file frame above the macro's memory frame, but
      identifiers in the included file still see the macro's
      params. `ss_top_memory_frame` is what makes this work after
      the migration -- it walks past any file frames on top to find
      the innermost memory frame, matching asm17's behavior.
  (Switching to dynamic scoping where outer macros' params are
  visible is a separate language change and is **not** part of
  Phase 4.) Commit.
- **4.7** Flip the parallel-write switch: stop writing parameters to
  the hash. Run full chain. Macro-heavy programs still build and
  self-host. Commit.
- **4.8** Delete `LABEL_TYPE_MACRO` and the parameter-hash code path.
  Delete `MACRO_ARG_BUF` and the `$0500-$05FF` region — args go
  directly into the frame at push time, no intermediate buffer
  needed (push the frame first with args parsed in-place, or use a
  small in-frame staging area; design choice in 4.4).
- **4.9** Verify with the leak test from 4.2: macro-heavy assembly
  no longer grows the heap with per-invocation param entries.
- **4.10** Reclaim or document `$0500-$05FF`. Update memory layout
  comment in `asm.asm`.

Commits per task. Full chain + all tests green at each.

## Phase 5 — Cleanup and documentation

- **5.1** Update `CLAUDE.md` memory map section to reflect freed
  regions and the merged stack.
- **5.2** Update `BOOTSTRAP-OVERVIEW` if it references any renamed
  symbols.
- **5.3** Sweep for stale references to `EXPANSION_ID16` if all uses
  are now removed (note: macro-locals still use it; that's the
  deferred work, leave intact).
- **5.4** Re-read `macro_local_design_notes.md` and add a one-line
  note about which prerequisites are now satisfied.

## Order, dependencies, exit criteria

Phases are sequential. Within a phase, tasks should be sequential
unless explicitly independent.

Each phase ends with:

- All commits pushed (well — committed; we never push) on
  `text-editor` branch (or whatever branch we pick at start).
- `./asmtestgen.sh` green (self-hosting verified).
- `python3 run_tests.py -q` green.
- File stack test suite green.
- A one-line note in this plan's status section.

## Risks and watchouts

- **Determinism between passes** is critical for the merged stack as
  it is today. Pre-flight any change with the assertion that pass 1
  and pass 2 produce identical frame chain shapes at any given
  source position.
- **`MACRO_ARG_BUF` is currently used to capture args before
  `push_label_scope` runs**, because parsing args needs the parent's
  scope. After Phase 4, the merged push order changes: parse args in
  parent's scope, build the frame with the args already in place,
  then push the frame. Verify nested-macro arg evaluation against
  Phase 4's first test.
- **The component test program reuses `source_stack.asm`** (renamed
  from `file_stack.asm` in Phase 1). The test program and the
  assembler must stay in sync; sweep both together for any push/pop
  contract changes after Phase 1.6.
- **The `CHECK_FOR_OUT_OF_MEMORY` macro** is defined per-program.
  Phase 0.3 replaced the test program's no-op stub with a real check
  driven by `OOM_LIMIT16`, observable via the `oom` mode.
- **`push_memory_source` calling convention is non-obvious.** The
  caller must leave `SS_MEM_PTR16` at the parent's value at the
  moment of push, then install the new buffer pointer afterwards;
  the bug found in Phase 0.4's `setup_memory_source` was caused by
  reversing this order. Phase 1.6 documents the contract; any
  Phase 3 push helper that wraps it must follow the same rule.

## Status (filled in as work proceeds)

- [x] Phase 0 — test coverage shoring (complete; added frames mode, balance
  tests, OOM injection mode, and top-frame-size visibility for the future
  payload work; also fixed a memory-above-memory ordering bug in the test
  program's setup_memory_source)
- [x] Phase 1 — rename (complete; file_stack.asm -> source_stack.asm,
  FILE_STACK -> SOURCE_STACK, FS_* -> SS_*, file_stack_* routines ->
  source_stack_* / push_file_source, pop_source alias dropped, test
  artifacts moved into 17/tests/source_stack/, comments and README swept)
- [x] Phase 1.6 — pre-Phase-2 cleanup (complete; documented
  push_memory_source's parent-pointer-on-entry contract and noted it
  at the macro_expansion call site, tightened the source_stack.asm
  module header, expanded push_source_frame's leading comment to
  call out its internal status and full input preconditions)
- [x] Phase 2 — abstraction refactor (complete; 2.1 added frame_size byte
  at offset 0; 2.2 extracted ss_alloc_frame / ss_free_frame and dedup'd
  the size calc by handing SS_TEMP16 from check_source_frame_room into
  push_source_frame; 2.3 added the 2-entry on_pop vtable indexed by
  curr_type, dispatched via ss_invoke -- root cause of an interim
  regression was the dispatch's TAX clobbering X across pop_source,
  fixed by bracketing with TXA/PHA + TYA/PHA; 2.4 added ss_walk_frames
  / ss_walk_frames_by_type and made the test program's print_frames
  use the generic walker; 2.5 replaced the SS_POP_MEMORY_HOOK
  compile-time alias with runtime ss_install_memory_pop, called from
  asm.asm's startup with pop_label_scope. Phase 4's macro-frame
  payload work will reuse this install API.)
- [x] Phase 3 — stack merge (complete; 3.1+3.2 added payload-bearing
  memory frames -- SS_PAYLOAD_SIZE / SS_PAYLOAD16 zero-page params,
  push_memory_source_with_payload entry point, and the @payload_memory
  test directive plus 6 new source_stack tests. 3.3+3.4 had
  expand_macro stage a 5-byte activation payload (LABEL_SCOPE16,
  CACHED_HASH, MACRO_ENTRY16) at MACRO_ACTIVATION and push it via
  push_memory_source_with_payload in a single step, replacing
  push_label_scope + push_memory_source; check_macro_recursion was
  rewritten to walk the source-stack chain via ss_walk_frames_by_type.
  3.5 collapsed into 3.4 (the new pop_label_scope_from_frame is the
  hook). 3.6 deleted SCOPE_STACK / SCOPE_PTR16 / SCOPE_LIMIT /
  SCOPE_ENTRY_SIZE / push_label_scope / pop_label_scope and renamed
  init_scope_stack to init_scope_state. 3.7 (delete MACRO_ENTRY16)
  was determined not yet applicable -- the var still serves
  expand_macro's setup as a save/restore anchor for MACRO_DEF_PTR16
  during the param parse/copy split; revisit during Phase 4. 3.8
  reclaimed \$0400-\$04FF (documented as free in asm.asm). 3.9 deleted
  err_macro_nesting_too_deep (error 34) and updated the test that
  expected it -- 52-level macro recursion now assembles successfully
  rather than overflowing a separate scope stack. Mid-migration bug
  caught by the 489-test suite: the new check_macro_recursion
  initially tail-called ss_walk_frames_by_type which clobbers X;
  expand_macro relied on X surviving, so the next push_file_source
  grabbed garbage as parent handle. Fixed by saving X around the walk
  in check_macro_recursion. asm.out: 7315 bytes (well below the
  pre-Phase-3 baseline -- the deletions outweigh the new payload
  infrastructure).)
- [x] Phase 4 — parameter activation frames (complete; 4.1 added the
  four scoping-invariant tests (shadowing, non-leakage direct + via
  .include); 4.3 extracted resolve_identifier as the identifier
  lookup chokepoint; 4.4 staged parameter slots in MACRO_ACTIVATION
  alongside scope_block + arg_count, with a runtime guard for the
  1-byte frame_size limit; 4.6+4.7 added ss_top_memory_frame and
  ss_lookup_param_slot, switched resolve_identifier to consult the
  innermost macro frame's slots before the global hash, and removed
  the LABEL_TYPE_MACRO hash adds in expand_macro Phase 2 (the
  user-facing motivation for this whole plan -- macro parameters no
  longer leak per-invocation heap entries); fixed parse_term
  IS_FWDREF clobbering so forward-ref args still propagate the flag
  through the new slot path; 4.5 (instrumented test) skipped because
  4.6+4.7 landed in the same commit; 4.8 deleted LABEL_TYPE_MACRO
  and shrank MACRO_ACTIVATION to a 32-byte buffer at \$0690 (max
  MACRO_MAX_ARGS=8 args, matching the documented cap; the
  assembler's own source uses at most 3 args); 4.9 added the leak
  verification test (macro_param_no_per_invocation_heap_leak: 30
  invocations under small_heap, would OOM pre-4.7); 4.10 reclaimed
  \$0500-\$05FF (no longer MACRO_ARG_BUF; documented as free in
  asm.asm). Counts: 492 v17 asm tests, 55 source_stack; v17
  self-hosts; preexisting opendir readonly_file failure aside,
  every test green throughout.)
- [x] Post-Phase-4 follow-up: macro-nesting / max-name tests + frame
  layout reorg. Added macro_nesting_overflow (deep nesting now reaches
  out-of-memory naturally), macro_max_name_max_args_at_frame_limit and
  macro_name_too_long (verifying a 127-char name + 8 args still fits
  the 1-byte frame_size). Then reorganized the source-stack frame:
  pre-reorg layout was [size, name\0, curr_type, prev_type, prev_line]
  which forced every walker (recursion check, activation lookup,
  traceback) to scan past a variable-length name. New layout puts the
  fixed header up front -- [size, curr_type, prev_type, prev_line_L,
  prev_line_H, name\0, prev_data, payload] -- so curr_type reads as a
  single (TABP16),Y at Y=1. Updated push_source_frame, pop_source's
  prev_data scan (now starts at offset 5), ss_walk_frames_by_type,
  ss_top_memory_frame, errors.asm's SHOW_FRAME_NAME, and the
  source_stack test program's print_traceback / print_frame_callback.
  494 v17 asm tests + 49 source_stack tests still green; self-host
  (asm.out == asm_2.out) verified.
- [x] Phase 5 — cleanup (5.1 updated CLAUDE.md memory map: corrected
  TOKEN/LHASHTAB addresses, documented the freed $0400-$05FF regions,
  switched "file stack" / FS_P16 references to "source stack" / SS_P16,
  noted the frame_size-driven O(1) walk; 5.2 BOOTSTRAP-OVERVIEW only
  references "file stack" historically in the v08 milestone row, no
  edit needed; 5.3 swept 17/README-BOOTSTRAP -- removed
  LABEL_TYPE_MACRO from the constants list, reworded recursion
  detection from "walking scope stack" to "walking the source-stack
  chain", added a line about parameters living as activation slots;
  EXPANSION_ID16 left intact since macro-locals still use it; 5.4
  appended a status block to macro_local_design_notes.md noting
  prerequisites 1-3 are satisfied and item 4 (EXPANSION_ID removal)
  is still the deferred work's responsibility.)
- [x] Post-Phase-5 follow-up: O(1) macro-frame lookup + delete
  MACRO_ACTIVATION buffer + raise MACRO_MAX_ARGS.
  Step 1: added MACRO_LOOKUP_FRAME16 (zp word) -- saved on macro
    push, restored on pop, untouched by file pushes -- and switched
    resolve_identifier from a per-call ss_top_memory_frame walk to
    a direct pointer read. ss_top_memory_frame deleted. Caught a
    latent bug where the previous "X clobbered" docstring on
    ss_lookup_param_slot didn't actually clobber X, so callers
    depended on it; the step-2 iteration counter would have
    introduced real X-clobbering, fixed via TXA/PHA + PLA/TAX.
  Step 2: macro definitions now lead with a 1-byte parameter count
    instead of a trailing empty-string sentinel. dir_macro reserves
    the count byte and bumps it in place per param;
    ss_lookup_param_slot reads N from the def via MACRO_ENTRY16;
    expand_macro reads N from the def into MACRO_ARG_REMAIN and
    drives Phase 1 with DEC/BEQ. The redundant Phase 2 walk was
    deleted (Phase 1 now leaves MACRO_DEF_PTR16 directly on the
    body). show_macros (debug build) updated to walk by count.
  Step 3: deleted MACRO_ACTIVATION (\$0690-\$06AF) entirely. The
    activation payload (slots + scope tail) is written directly
    into the unallocated source-stack memory at SS_P16 -
    payload_size, then push_memory_source_reserve_payload (a new
    source_stack.asm entry point) commits the frame in place. SS_P16
    / SS_SRC_TYPE / SS_MEM_PTR16 / SS_CURR_LINE16 stay parent's
    during arg parsing -- read_char keeps reading from the
    invocation site, errors fire with the correct line. arg_count
    dropped from the payload (frame is canonical-by-def now);
    payload tail shrank by 1 byte. MACRO_MAX_ARGS bumped 8 -> 64
    (binding constraint is the 1-byte frame_size: 15 + name_len +
    3*N <= 255). dir_macro enforces the 64 cap at definition time.
    Tests updated: macro_args_at_cap (64 args succeed),
    macro_args_above_cap_at_def (65 params at .macro time raise
    err_too_many_arguments), macro_max_name_args_fit_frame
    (description rewritten -- frame_size is the upper-end
    constraint, not the old 8-arg cap).
  Step 4: check_macro_recursion now walks the prev_macro_lookup
    chain instead of ss_walk_frames_by_type. File frames don't
    appear in the chain so they're skipped for free.
    ss_walk_frames_by_type and SS_WALK_FILTER had no callers left,
    so deleted from source_stack.asm. ss_walk_frames stays -- the
    test program's print_frames mode still uses it.
  Step 5: refreshed CLAUDE.md memory map (\$0690 now free) and
    17/README sections on macro definition / expansion / source
    stack to describe the new push-after-write flow, the count-byte
    def layout, and MACRO_LOOKUP_FRAME16 as the lookup anchor.
    494/494 v17 asm tests, both regular and debug self-host clean
    throughout.
