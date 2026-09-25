# Editor Performance Plan

## Completed

### Incremental line pointer adjustment

When inserting/deleting a non-newline character, line pointers after the edit
point shift by +1/-1. `buf_adjust_lines_inc` and `buf_adjust_lines_dec` walk
LINE_TBL and adjust each pointer, replacing a full `buf_rebuild_lines` scan.

For a 318-line file: ~12K cycles vs ~194K cycles.

### Page-at-a-time byte shifting

`buf_shift_right_16` and `buf_shift_left_16` use Y-indexed inner loops to process
up to 256 bytes per page, avoiding per-byte 16-bit pointer manipulation.

~16-18 cycles/byte vs ~47 cycles/byte.

### Unified insert-mode batching

All insert-mode editing keys (printable, Enter, BS, DEL) are handled by a
single `insert_batch` handler. On each keystroke, it collects pending keys
from the input buffer and consolidates them on-the-fly into canonical form:

```
[back N] [insert BATCH_BUF[0..len-1]] [fwd N]
```

- **Printable/Enter**: appended to `BATCH_BUF`
- **BS**: cancels the last buffered char if any, otherwise increments `back`
- **DEL**: increments `fwd`
- **Other key**: pushed back, collection stops

Up to `BATCH_MAX` (32) keys are consumed per batch. The on-the-fly
consolidation means BS can cancel a just-typed character without ever
touching the buffer (e.g. `type A, BS, type B` → inserts just "B").

Execution computes `net = insert_len - back - fwd` and performs a single
`buf_shift_right_16` (net > 0) or `buf_shift_left_16` (net < 0), then
copies `BATCH_BUF` into place. Two post-operation paths:

- **Fast path** (no newlines crossed): incremental `buf_adjust_lines_inc`
  or `buf_adjust_lines_dec`. O(line_count) pointer walk.
- **Newlines path** (any newline inserted or deleted): full
  `buf_rebuild_lines` + `mark_adjust_delete`/`mark_adjust_insert`.

This reduces N mixed keystrokes from `N * (shift + rebuild + render)` to
`1 * (shift + render)`, regardless of key type mixing. Previous handlers
required returning to the main loop whenever the key type changed (e.g.
type → BS → type was 3 separate operations).

### Batch delete in normal mode

In normal mode, `count_pending_key` (in input.asm) checks for additional
buffered matching keys after x. Pending deletes are counted and executed
with a single `buf_shift_left` via `buf_delete_chars`, with one
`buf_adjust_lines_dec` call for the batch.

### Indent/unindent range repaint

`>>`, `<<`, `:N,M>`, `:N,M<`, and their undo use a dedicated render path
(`RENDER_FLAG=$0B`): the handler pre-computes the affected range's screen
rows; after the edit only those rows are repainted. If wrapping changed
the row count, the region below is scrolled by the difference and only
the range plus newly exposed rows are drawn. No-op shifts (nothing to
remove, all-empty lines) skip both the repaint and the MODIFIED flag.

### Direct echo for r and ~

`r` and `~` write their result chars straight to the terminal (no repaint)
while staying inside the cursor's wrap row; every visited char is echoed
so the terminal cursor tracks the buffer position. On hitting the wrap
boundary or an unprintable char, the rest of the line is repainted from
that column only.

### ICH/DCH shifting for in-line edits

Insert-mode typing, BS and DEL (including whole type-ahead batches) and
normal-mode `x` / `X` hand the render a hint: `SHIFT_NET` (cells inserted
or deleted at `RENDER_FROM_COL16`) and `SHIFT_WRITE` (new cells written
there). `render_line_shift` then shifts each row of the line with ICH
(`ESC[n@`) or DCH (`ESC[nP`) and writes only the new cells plus the cells
carried across a row boundary, instead of resending everything after the
edit point. A batch shifts once per row. Each row compares byte costs and
resends instead when that is cheaper (short tails, large deletes). Rows
opened or closed by a row-count change are handled by the existing scroll
paths first. See `ich-dch-plan.md`.

Typing two characters at column 5 of a 3-row line on a 40-column screen
goes from about 115 bytes of row content to about 30.

## Future Work

### Step 4: Gap buffer

**Problem:** Even with optimized shifting, inserting a character in a large
file requires moving all bytes after the edit point. This is O(file_size) per
keystroke.

**Design:** Replace the contiguous buffer with a gap buffer:

```
[text before cursor] [--- gap ---] [text after cursor]
```

- **Insert:** Write character at gap start, shrink gap by 1. O(1).
- **Delete:** Expand gap by 1. O(1).
- **Move cursor:** Shift bytes across the gap boundary. O(distance moved).
  Between keystrokes the cursor typically moves by at most one line, so
  this is cheap.

**Data structures:**
- `GAP_START16`: pointer to first byte of gap.
- `GAP_END16`: pointer to first byte after gap.
- Buffer content is `[TEXT_BUF .. GAP_START16)` + `[GAP_END16 .. BUF_END16)`.

**Line table:** LINE_TBL stores absolute buffer positions. Positions before
the gap are direct. Positions after the gap are stored as their actual
address (past the gap), so `buf_get_line_ptr` needs gap-aware translation:
if the stored pointer >= GAP_START16, the real content is at
`stored_ptr + (GAP_END16 - GAP_START16)`.

Alternatively, store positions as logical offsets (pretending the gap
doesn't exist) and translate on access. The first approach is simpler since
most line table operations just compare or iterate.

**Affected code:**
- `editor/buffer.asm`: `buf_shift_right_16`/`buf_shift_left_16` become
  O(1) gap adjustments. `buf_get_line_ptr` needs gap translation.
  `buf_rebuild_lines` scans non-gap regions.
- `editor/render.asm`: `render_line_chars` reads buffer content that may
  span the gap. Needs to check if current line crosses the gap and
  handle the split.
- `editor/insert.asm`: `insert_batch` writes to `BATCH_BUF` and copies
  into the buffer, so it needs gap-aware copy. The collection phase is
  unchanged.
- `editor/normal.asm`: Cursor movement may need to shift bytes across
  the gap, but the high-level logic stays the same.

**Incremental line adjustment with gap buffer:** With a gap buffer,
buf_adjust_lines_inc/dec are no longer needed since insert/delete don't
shift the buffer. The line table just needs one new entry (for newline
insert) or one removed entry (for newline delete), plus the gap position
bookkeeping.

**Complexity:** This is a significant refactor. Plan in detail after
evaluating whether steps 1-3 provide sufficient performance.
