# Editor Normal Mode Audit Plan

> **Attic note:** historical. Paths (`22/`, `23/`, `editor/`, `assembler2/`) are from the old assembler2 layout; the live code is `asm/` (stages 00-17) and `editor/`. See `attic/assembler2/README.md`.


## 1. Operation-by-Operation Batching Analysis

### 1.1 Movement Commands (all are read-only, no buffer shifts needed)

| Command | Batching | Mechanism | Status |
|---------|----------|-----------|--------|
| h/LEFT | Yes | `get_batched_count` → `move_left_x` | OK |
| l/RIGHT | Yes | `get_batched_count` → `move_right_x` | OK |
| j/DOWN | Yes | `get_batched_count` → `move_down_x` | OK |
| k/UP | Yes | `get_batched_count` → `move_up_x` | OK |
| w | Yes | `get_batched_count` → `word_forward_x` | OK |
| b | Yes | `get_batched_count` → `word_backward_x` | OK |
| e | Yes | `get_batched_count` → `word_end_x` | OK |
| 0/HOME | No batching needed | Idempotent (sets col=0) | OK |
| $/END | No batching needed | Idempotent (sets col=len-1) | OK |
| ^  | No batching needed | Idempotent | OK |
| G | No batching needed | Uses count prefix only | OK |
| gg | No batching needed | Idempotent (combo, goes to top) | OK |
| Ctrl-F/PgDn | Yes | `get_batched_count` → loop | OK |
| Ctrl-B/PgUp | Yes | `get_batched_count` → loop | OK |
| /,?,n,N | No batching needed | Interactive/idempotent | OK |
| m+X | No batching needed | Sets mark (combo with wildcard) | OK |
| '+X | No batching needed | Goes to mark (combo with wildcard) | OK |

**Movement verdict:** All movement commands properly batch. No buffer operations, so no efficiency concern.

### 1.2 Line Delete (dd)

**Batching:** Yes, via `batch_pending_pairs` (flags=$03)
**Mechanism:** `do_dd` at normal.asm:234
- Non-batched: `yank_delete_current_lines` (single yank+delete)
- Batched: `delete_current_lines` for (total-1) lines, then `yank_delete_current_lines` for last 1

**Buffer shifts:**
- Non-batched path: 1 shift (via `buf_delete_lines` → `buf_shift_left_16`) + 1 `buf_rebuild_lines` -- OK
- Batched path: **2 shifts** -- `delete_current_lines` does 1 shift+rebuild, then `yank_delete_current_lines` does another shift+rebuild

**ISSUE: Batched dd performs 2 buffer shifts and 2 line rebuilds instead of 1.**

**Fix approach:** Compute total lines to delete, yank just the last line's worth, then delete all lines in one operation. Something like:
1. Yank 1 line at FILE_LINE16 + (total-1)
2. Delete total lines at FILE_LINE16
This would require separating the yank from the delete in the yank_delete path.

### 1.3 Character Delete (x/DEL)

**Batching:** Yes, via `count_pending_key` in `normal_delete_char`
**Mechanism:** normal.asm:193 → normal_util.asm:606 `batched_char_delete`
- Non-batched: single `compute_char_range_forward` + `apply_char_operator(OP_DELETE)`
- Batched: `delete_at_cursor` for (total-1), then `apply_char_operator` for last 1

**Buffer shifts:**
- Non-batched: 1 shift (via `yank_delete_at_cursor` → `delete_at_cursor`) -- OK
- Batched: **2 shifts** -- `delete_at_cursor` for first batch, then `yank_delete_at_cursor` for last char

**ISSUE: Batched x performs 2 buffer shifts instead of 1.**

**Fix approach:** Compute total chars, yank last 1 char, then delete all chars in one shift. Or: delete (total-1) chars and yank+delete last char, but compute the combined range upfront and do a single shift for the entire range.

### 1.4 Delete to EOL (D)

**Batching:** No batching support
**Current:** `normal_delete_to_eol` at normal.asm:218 -- uses `apply_char_operator(OP_DELETE)`

**No batching concern:** D is idempotent after the first execution (line becomes empty, subsequent D has nothing to do). Typing `DDD` rapidly would: first D deletes to EOL, second D finds cursor at/past end via `check_cursor_in_line` → BCS and does nothing. So the result is correct even without explicit batching.

**Status:** OK -- no batching needed due to idempotence.

### 1.5 Word Delete (dw, db, de)

**Batching:** Yes, via `batch_pending_pairs` (flags=$03)

**dw** (normal_edit.asm:703):
- Non-batched: `compute_multiline_word_range_forward` + `apply_char_operator(OP_DELETE)` → 1 shift
- Batched: `delete_at_cursor` for (total-1) words, then `apply_char_operator` for last word → **2 shifts**

**db** (normal_edit.asm:747):
- Same pattern as dw but backward → **2 shifts when batched**

**de** (normal_edit.asm:833):
- Same pattern as dw but word-end → **2 shifts when batched**

**ISSUE: All batched word deletes perform 2 buffer shifts instead of 1.**

**Fix approach:** Same strategy as x -- compute combined range for all words, yank the last word's range, then delete the entire combined range in one operation.

**Additional concern for db:** The backward word range computation modifies CURSOR_COL16 (moves cursor to start of range). In the batched path, after deleting (total-1) words, the cursor has moved. The subsequent single-word backward range computation starts from the new cursor position, which is correct. However, each intermediate `delete_at_cursor` does a shift+rebuild, which is inefficient.

### 1.6 Yank Line (yy)

**Batching:** Yes, via `batch_pending_pairs` (flags=$00, bit 0 set for yy)
**Mechanism:** normal_move.asm:230 `do_yy`
- If BATCH_EXTRA > 0: caps count to 1 (only last yank matters)
- Calls `yank_add_lines`

**Buffer shifts:** 0 (yank is read-only)
**Status:** OK -- correctly handles batching semantics (last yank wins).

### 1.7 Word Yank (yw, yb, ye)

**Batching:** No explicit pair batching (flags=$00, bit 0 NOT set)

**yw** (normal_move.asm:248): Uses `get_count` only, no `batch_pending_pairs`
**yb** (normal_move.asm:265): Same
**ye** (normal_move.asm:283): Same

**ISSUE: yw, yb, ye have NO batching at all.** If you type `ywyw` rapidly, the second `yw` won't be batched. However, since yank is read-only and the last yank overwrites previous ones, the practical impact is minimal -- the second yw just overwrites the first yank. But note:
- The pending combo table entries for yw, yb, ye have flags=$00, so `batch_pending_pairs` is NOT called.
- This means BATCH_EXTRA is always 0 for these commands, and they always use the count prefix path.
- If typing `ywyw` rapidly: first yw processes, then clear_count restores BATCH_RESTORE_KEY=0, second yw starts fresh. This is correct because yank is idempotent (cursor doesn't move for yw/ye, and yb moves cursor but that's the correct semantic).

**Verdict:** OK for correctness. Could optimize by capping count to 1 when batched (like yy does), but since yank is read-only, the cost is just redundant computation, not redundant buffer shifts.

### 1.8 Paste (p, P)

**Batching:** Yes, via `count_paste_extras`
**Mechanism:** normal_edit.asm:6 `normal_paste_below` / :26 `normal_paste_above`

**Line paste below (p):**
- `get_count` + `count_paste_extras` → total count in BUF_TEMP16
- `yank_paste_below_n` → single `buf_shift_right_16` + N copies into gap + 1 `buf_rebuild_lines`
- 1 shift, 1 rebuild -- OK

**Line paste above (P):**
- Same pattern via `yank_paste_above_n`
- 1 shift, 1 rebuild -- OK

**Character paste below (p):**
- `do_char_paste_below` → `yank_paste_setup` + single `buf_shift_right_16` via `yank_paste_core` + 1 `buf_rebuild_lines`
- 1 shift, 1 rebuild -- OK

**Character paste above (P):**
- `char_paste_above` → `yank_paste_setup` + single `buf_shift_right_16` + interleaved/contiguous fill + 1 `buf_rebuild_lines`
- 1 shift, 1 rebuild -- OK

**Cursor position for batched paste:**
- Line paste below: `FILE_LINE16 += 1 + BATCH_EXTRA` -- moves to the line after the last pasted block, which matches iterative semantics (each p moves cursor one line down past the paste)
- Line paste above: no cursor adjustment -- stays at original line, which means all pasted content appears above. This is correct.
- Char paste below: contiguous insertion, cursor at last pasted byte. Correct.
- Char paste above: uses interleaved fill for single-line, contiguous fill for multi-line. Cursor at `insertion + total_size - 1 - BATCH_EXTRA`. This formula accounts for the fact that iteratively, each P inserts before cursor, pushing it right, so the final cursor position is at the last byte of the last non-interleaved paste.

**Status:** OK -- single shift, single rebuild, correct cursor positioning.

### 1.9 Toggle Case (~)

**Batching:** No explicit batching; uses `get_count` only
**Mechanism:** normal_edit.asm:278 `normal_toggle_case`

Currently loops through count chars, toggling each one in-place. No buffer shift at all (modifies bytes in place). No line rebuild needed (no structural change).

**ISSUE: No batching of rapid ~ presses.** If you type `~~~` rapidly, each ~ is processed independently. The count prefix works (3~ toggles 3 chars), but rapid typing doesn't combine.

**Fix approach:** Add batching via `get_batched_count` or `count_pending_key`. Since ~ is a single-key command (not a combo), it would use `get_batched_count` pattern. However, ~ is in the `normal_editing_keys` table (not pending_combo_keys), so it uses the regular dispatch path.

**Should use:** Change to use `get_batched_count` like h/l/j/k do. This would batch `~~~` into a single operation. Since ~ only modifies bytes in-place (no shifts), the efficiency gain is minimal, but it would be consistent.

**Correctness concern:** ~ advances cursor after each toggle. Batching must preserve this: `~~` at col 0 on "Hello" should toggle H and e, ending at col 2. With `get_batched_count`, the loop already handles this correctly.

**Status:** Missing batching but functionally correct. Low priority fix.

### 1.10 Join Lines (J)

**Batching:** No explicit batching; uses `get_count` only
**Mechanism:** normal_edit.asm:323 `normal_join_lines`

**CRITICAL ISSUE: Multiple buffer shifts and rebuilds per join.**
The join loop replaces each newline with a space one at a time:
1. Find line end → replace '\n' with ' '
2. `buf_rebuild_lines` (full rebuild!)
3. `mark_adjust_delete` for the joined line
4. Repeat for each additional join

For `3J`, this does 2 individual joins, each with its own `buf_rebuild_lines`. For batched `JJJ`, it would be 3 joins with 3 rebuilds (no batching at all since J is not in pending_combo_keys and doesn't use `get_batched_count`).

**Multiple issues:**
1. **No batching** of rapid J presses
2. **Multiple rebuilds** even with count prefix (one per join)
3. No buffer shift at all (replaces newline with space in-place), but full rebuild per iteration is expensive

**Fix approach:**
1. Add batching via `get_batched_count`
2. Process all joins in one pass: find each newline to replace, replace them all, then do a single `buf_rebuild_lines`
3. Do a single `mark_adjust_delete` for all removed lines

### 1.11 Substitute (s)

**Batching:** No explicit batching; uses `get_count`
**Enters insert mode**, so rapid `sss` wouldn't batch (first s enters insert, subsequent s's are insert-mode characters).

**Status:** OK -- enters insert mode, so batching not applicable.

### 1.12 Change to EOL (C)

**Batching:** No batching needed
**Enters insert mode** immediately. Idempotent if line is already empty.

**Status:** OK

### 1.13 Replace Char (r+X)

**Batching:** No pair batching (flags=$02 for r in combo table, bit 0 not set)
**Mechanism:** normal_edit.asm:405 `do_replace_char`

Loops through count chars, replacing each byte in-place. No buffer shift. The `r` entry in pending_combo_keys has flags=$02 (editing flag, but NOT batch flag).

**ISSUE:** No batching of `rXrX` sequences. Since r is a wildcard combo (second key is the replacement char), batching would only apply if the same replacement is used repeatedly, which is unusual. The flags don't have bit 0 set, so `batch_pending_pairs` is never called.

**Status:** OK -- batching wouldn't help (replacement char varies). Could theoretically batch `rXrX` where X is the same, but this is an edge case.

### 1.14 Change Line (cc, S)

**Batching:** No explicit pair batching (flags=$02 for cc)
**Wait -- checking:** cc entry is `'c', 'c', $02`. Flags = $02 means editing flag but NOT batch flag (bit 0 = 0). So `batch_pending_pairs` is NOT called for cc.

**Enters insert mode**, so batching not applicable for `cccc` (first cc enters insert).

**Status:** OK -- enters insert mode.

### 1.15 Indent (>>)

**Batching:** No explicit pair batching. Checking flags: `'>', '>', $02` -- flags=$02, bit 0 NOT set.

**ISSUE: No batching of `>>>>` sequences.** However, >> uses `get_count_clamp_lines` which respects count prefix. The implementation already does a single buffer shift for all lines (pre-scans, single `buf_shift_right_16`, redistributes). So `2>>` is already efficient.

**But `>>>>` (two rapid >> combos) won't batch.** The first >> processes with count=1, the second >> starts fresh. Each does one shift and one rebuild.

**Fix approach:** Add batch flag (bit 0) to >> entry. Then `batch_pending_pairs` would combine `>>>>` into a count=2 operation, which would do a single shift and rebuild.

**Status:** Missing batching for rapid >> presses. Medium priority.

### 1.16 Unindent (<<)

**Batching:** Same as indent -- flags=$02, bit 0 NOT set.
**Same issues as >>.**

**Status:** Missing batching for rapid << presses. Medium priority.

### 1.17 Word Change (cw, cb, ce)

**Batching:** None. Flags=$02 for all (editing flag only, no batch flag).
**All enter insert mode**, so batching not applicable.

**Status:** OK -- enter insert mode.

### 1.18 Open Line (o, O)

**No batching.** Enter insert mode immediately.
**Status:** OK

## 2. Efficiency Summary: Buffer Shifts and Line Rebuilds

| Operation | Non-batched | Batched | Target |
|-----------|-------------|---------|--------|
| dd | 1 shift, 1 rebuild | **2 shifts, 2 rebuilds** | 1 shift, 1 rebuild |
| x | 1 shift, 1 adj | **2 shifts, 2 adj** | 1 shift, 1 adj |
| dw | 1 shift, 1 rebuild/adj | **2 shifts, 2 rebuild/adj** | 1 shift, 1 rebuild/adj |
| db | 1 shift, 1 rebuild/adj | **2 shifts, 2 rebuild/adj** | 1 shift, 1 rebuild/adj |
| de | 1 shift, 1 rebuild/adj | **2 shifts, 2 rebuild/adj** | 1 shift, 1 rebuild/adj |
| J | N-1 rebuilds (count) | N rebuilds (no batch) | 1 rebuild |
| p/P | 1 shift, 1 rebuild | 1 shift, 1 rebuild | OK |
| >> | 1 shift, 1 rebuild | N shifts (no batch) | 1 shift, 1 rebuild |
| << | 1 shift, 1 rebuild | N shifts (no batch) | 1 shift, 1 rebuild |

## 3. Missing Batching Support

Commands that should support batching but don't (or that batch but still do multiple shifts):

| Priority | Command | Issue | Fix |
|----------|---------|-------|-----|
| High | dd (batched) | 2 shifts/rebuilds | Yank last line separately, delete all in one op |
| High | x (batched) | 2 shifts/adjustments | Compute combined range, yank last, delete all |
| High | dw/db/de (batched) | 2 shifts each | Same approach as x |
| High | J | No batching + N rebuilds with count | Add batching + single-pass join |
| Medium | >> | No batching | Add batch flag (bit 0) to combo entry |
| Medium | << | No batching | Add batch flag (bit 0) to combo entry |
| Low | ~ | No batching | Add `get_batched_count` |

## 4. Code Similarity / Divergence Analysis

### 4.1 dw, db, de share identical batched patterns

All three follow the exact same structure:
```
  get_count
  check_cursor_in_line (or equivalent)
  if BATCH_EXTRA = 0:
    compute_range (X = count)
    apply_char_operator(OP_DELETE)
  else:
    compute_range (X = count - 1)
    delete_at_cursor
    re-check
    compute_range (X = 1)
    apply_char_operator(OP_DELETE)
  clamp_cursor_col
  clear_count
```

**Opportunity:** Extract a generic `batched_word_operator` that takes a function pointer for the range computation. This could handle dw, db, de, and potentially cw, cb, ce (with OP_CHANGE instead of OP_DELETE).

### 4.2 yw, yb, ye share identical non-batched patterns

All three:
```
  get_count
  check_cursor_in_line (or equivalent)
  compute_range (X = count)
  apply_char_operator(OP_YANK)
  clear_count
```

### 4.3 delete_at_cursor duplicates logic in batched paths

`delete_at_cursor` (normal_util.asm:524) scans for newlines, shifts left, and either does incremental adjust or full rebuild. This is called in the "first N-1" path of every batched delete, followed by a separate yank+delete for the last item. Consolidating into a single operation would avoid the duplication.

### 4.4 Paste below/above share setup code

`normal_paste_below` and `normal_paste_above` (normal_edit.asm:6,26) have parallel structure for both line and char paste paths. The char paste paths differ in insertion point calculation (after cursor vs at cursor) but share setup/cleanup.

## 5. Proposed Refactoring Strategy

### Phase 1: Fix batched efficiency (single shift)

For dd, x, dw, db, de -- restructure batched paths to:
1. Compute the combined range for all N operations
2. Yank the last operation's range (for correct yank-buffer semantics)
3. Delete the entire combined range in one buffer shift

This is the highest-impact change. For dw/db/de, the range computation is complex (multi-line word boundaries), so the simplest approach may be:
- Save cursor state
- Run the motion N-1 times to find the end of the "first N-1" range
- Yank from that point for 1 word
- Restore cursor to original position
- Compute combined range = original cursor to end of Nth word
- Single delete

### Phase 2: Add missing batching

- J: Add `get_batched_count`, rewrite to single-pass
- >>: Set bit 0 in flags ($02 → $03)
- <<: Set bit 0 in flags ($02 → $03)
- ~: Add `get_batched_count`

For >> and <<, simply setting the batch flag should work because the existing `get_count` call will pick up the combined count, and the implementation already handles multi-line operations efficiently.

### Phase 3: Extract shared patterns

Create a generic `batched_word_delete` helper that takes a range-computation function pointer and an operator type:
```
; Input: JUMP_TARGET16 = range computation function
;        A = operator (OP_DELETE or OP_CHANGE)
; Handles: get_count, batch_extra check, compute range, yank last, delete all
batched_word_operator:
  ...
```

This would consolidate do_dw, do_db, do_de into callers that just set up the function pointer and call the generic helper.

## 6. Test Coverage Gaps

### 6.1 Tests that should be added

| Test | What it verifies |
|------|-----------------|
| Batched dd cursor position | `dddd` on 5-line file: verify cursor ends at correct line |
| Batched dd yank buffer | `dddd`: verify yank contains only the last line |
| Batched dw text result | `dwdw` on "hello world foo": verify correct text |
| Batched dw yank buffer | `dwdw`: verify yank contains only the last word |
| Batched db text result | `dbdb` with cursor at end |
| Batched de text result | `dede` with cursor at start |
| Batched x yank buffer | `xxxx`: verify yank contains only last char |
| Count prefix dd | `3dd` on 5-line file: verify 3 lines deleted |
| Count prefix dw | `2dw`: verify 2 words deleted |
| Batched J text result | `JJJ` on multi-line: verify correct joining |
| Count J text result | `3J`: verify joins 3 lines |
| Batched >> | `>>>>` verify correct indent |
| Batched << | `<<<<` verify correct unindent |
| Batched ~ | `~~~` verify correct case toggles |
| Mixed count + batch dd | `2dd` + batched `dd` = 3 lines deleted total |
| Batched p line paste | `ppp` verify 3 copies pasted, cursor correct |
| Batched P line paste | `PPP` verify 3 copies pasted, cursor correct |
| Batched p char paste | `ppp` with char yank, verify correct text and cursor |
| Edge: batched dd at EOF | `dddd` when fewer lines remain than requested |
| Edge: batched x at EOL | `xxxxx` when fewer chars remain |
| Edge: batched dw at EOL | `dwdw` when word extends to line end |
| Edge: batched db at BOL | `dbdb` when at start of line |

### 6.2 Existing test coverage

The test file has good coverage for:
- Basic x batching (delete multiple chars)
- Insert mode mixed batching (BS, DEL, printable, Enter)
- Render optimization (batch reduces redraws)
- Count prefix + batch combinations for movements (j, l, w)
- Count prefix + batch dw
- Paste with count + batch (2p + batch p)

Missing coverage for:
- dd batching semantics (yank buffer correctness)
- db/de batching
- J batching/count
- >>/<<  batching
- ~ batching
- Mixed count + batch for editing commands

## 7. Implementation Order

1. **Add tests first** for current behavior (document what exists)
2. **Fix >> and << batching** (trivial flag change, add tests)
3. **Fix J batching and count efficiency** (add batching, single-pass)
4. **Fix dd batched efficiency** (single shift)
5. **Fix x batched efficiency** (single shift)
6. **Fix dw/db/de batched efficiency** (single shift)
7. **Add ~ batching** (minor improvement)
8. **Extract shared word-operator pattern** (refactor for code sharing)
9. **Run full test suite** after each change to verify no regressions
