# Editor Performance Plan

## Completed

### Incremental line pointer adjustment

When inserting/deleting a non-newline character, line pointers after the edit
point shift by the same amount. `buf_adjust_lines_apply` walks LINE_TBL and
adds that signed delta to each pointer, replacing a full `buf_rebuild_lines`
scan.

For a 318-line file: ~12K cycles vs ~194K cycles.

### Page-at-a-time byte shifting

`buf_shift_right_16` and `buf_shift_left_16` (via `mem_copy_down`) use
Y-indexed inner loops to process up to 256 bytes per page, avoiding per-byte
16-bit pointer manipulation.

~16 cycles/byte vs ~47 cycles/byte.

### Unified insert-mode batching

All insert-mode editing keys (printable, Tab, Enter, BS, DEL) are handled by
one batch handler, `insert_handle_key`. On each keystroke, it collects
pending keys from the input buffer and consolidates them on-the-fly into
canonical form:

```
[back N] [insert BATCH_BUF[0..len-1]] [fwd N]
```

- **Printable/Enter**: appended to `BATCH_BUF`
- **BS**: cancels the last buffered char if any, otherwise increments `back`
- **DEL**: increments `fwd`
- **Other key**: ends the batch and is pushed back (a batch's first key
  that is not an editing key is dispatched through `insert_keys` instead)

Up to `BATCH_MAX` (32) keys are consumed per batch, and no more than the
buffer's free bytes: a batch then always fits, and a char that does not
fit comes alone and is refused as when typed alone. The on-the-fly
consolidation means BS can cancel a just-typed character without ever
touching the buffer (e.g. `type A, BS, type B` → inserts just "B").

Execution computes `net = insert_len - back - fwd` and performs a single
`buf_shift_right_16` (net > 0) or `buf_shift_left_16` (net < 0), then
copies `BATCH_BUF` into place. Two post-operation paths:

- **Fast path** (no newlines crossed): incremental `buf_adjust_lines_apply`
  with the signed net. O(line_count) pointer walk.
- **Newlines path** (any newline inserted or deleted): full
  `buf_rebuild_lines` + `mark_adjust_delete`/`mark_adjust_insert`.

This reduces N mixed keystrokes from `N * (shift + rebuild + render)` to
`1 * (shift + render)`, regardless of key type mixing. Previous handlers
required returning to the main loop whenever the key type changed (e.g.
type → BS → type was 3 separate operations).

### Batch delete in normal mode

In normal mode, `count_pending_key` (in input.asm) checks for additional
buffered matching keys after x. Pending deletes are counted and executed
with a single `buf_shift_left_16` via `delete_at_cursor`, with one
`buf_adjust_lines_apply` call for the batch.

### Range deletes scroll as dd does

`:N,Md` (and `:d`) takes dd's path, `yank_delete_current_lines`, and its
render too: `precompute_delete_scroll` counts the rows of the lines
before they go and `finish_delete_scroll` sets `RF_DEL`, so the rows
below scroll up and only the rows that exposes are drawn. `:4,6d` on a
24x80 screen of 60-char lines sends 312 bytes instead of 1,558.

### Line inserts, splits and joins as one block

A change that adds or removes lines at the cursor line is drawn as an
in-line edit of a block of lines (`render_rows_resized`): the rows below
the block move by its change in rows, and the block is drawn from its
first changed column. `o`, `O`, `p`, `P` and the undo of `dd` are a
block of new lines that had no rows before (`RF_INS`); the undo of `J`,
of `cc` and of a char delete over line breaks, and a char paste of
several lines, are the cursor line and the lines after it in place of
the line's old rows (`RF_SPLIT`); every join is the joined line in
place of all their rows (`RF_JOIN`). So the undo of `J` draws from the
join point and a multi-line `P` from the paste column, and a block
drawn whole opens its new rows at its first row, where the drawing
starts. Over about 20,000 random sessions the bytes fall 0.27% (1.2%
for sessions of joins and their undo); a few near the bottom row send
up to 24 bytes more, where a block that reaches the status bar still
moves its rows.

### Indent/unindent range repaint

`>>`, `<<`, `:N,M>`, `:N,M<`, and their undo use a dedicated render path
(`RENDER_FLAG` = `RF_RANGE`): the handler pre-computes the affected range's screen
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

Insert-mode typing, BS and DEL (including whole type-ahead batches),
every delete at the cursor that stays within its line (`x`, `X`, `dw`,
`db`, `de`, `d0`, `D`, `s`, `cw`... and their redo, the undo of `p` / `P`
and of typed text), a char paste with no newline (`p`, `P`, their redo,
the undo of a char delete) and `>>` / `<<` of one line hand the render a
hint: `SHIFT_NET` (cells inserted or deleted at `RENDER_FROM_COL16`) and
`SHIFT_WRITE` (new cells written there). `render_line_shift` then shifts each row of the line with ICH
(`ESC[n@`) or DCH (`ESC[nP`) and writes only the new cells plus the cells
carried across a row boundary, instead of resending everything after the
edit point. A batch shifts once per row. Each row compares byte costs and
resends instead when that is cheaper (short tails, large deletes). A row
after one written to its end by chars follows by the terminal's wrap, and
a batch that nets no shift stops after its new cells. Rows opened or
closed by a row-count change are handled by the existing scroll paths
first. See `ich-dch-plan.md`.

Typing two characters at column 5 of a 3-row line on a 40-column screen
goes from about 115 bytes of row content to about 30. Near the start of
such a line, `dw` takes a 98-byte frame where the rewrite took 146, `P`
of a word 85 (156), u after `x` 37 (116), and `>>` 79 (158). Over the
audit's 432 repaint scenarios (dw, db, de, D, d0, s, cw, x, p, P, u,
`>>`, `<<`... on short and wrapped lines at 10x40 and 24x80) the frames
went from 62,753 bytes to 37,858.

### Edits that move the view down

An edit on the bottom rows that pushes the cursor below the screen (`o`,
Enter, `p`, `J` on the bottom row, typing past the end of the last row)
used to redraw the whole screen when it changed the line count. The text
before the edit's first changed cell is as it was, so `render_scroll_up`
scrolls the text area up by the rows the view moved (walked over lines
that did not change) and draws only from that cell (or from the first
row the scroll exposed, if that comes first) to the bottom: `o` on the
bottom row of a 24x80 screen of 48-char lines sends 113 bytes instead of
1,268. The cell is found from the cursor (`rows_to_cursor`,
`change_cell_row`, shared with the Enter split): in the cursor line at
`RENDER_FROM_COL16`, or for an Enter batch in the line it split. A first
change on the top row redraws in full, as nothing keeps its place. An
in-line edit of a line that starts above the view (a line taller than
the screen) is drawn from its change too, the view moved or not: typing
40 chars at the end of a 399-char line at 10x40 sends 1,600 bytes
instead of 15,052.

Typed-ahead `p` keys of a line yank (`pp`, `ppp`) paste their copies in
one frame after the line the cursor was on, with the cursor on the last:
the render sees an Enter batch that split that line at its end
(`RF_ENTER` from its length), so the rows below scroll down and only the
copies are drawn. `pp` in the middle of a 24x80 screen of 48-char lines
sends 189 bytes instead of 1,274. With a count (`3pp`) the copies go on
past the cursor line, and the screen is redrawn.

### Status bar: only what changed

`status_build` builds the status bar's text into `STATUS_SHADOW` ($0380,
the upper half of the command buffer's page) and compares it with the
text already on the row; `status_send` then sends it from the first
column that changed, with `ESC[K` only when the old text was longer or is
unknown (after a message, a prompt or `:marks`). A cursor move sends just
the new position: `j` on a 10x40 screen goes from 68 bytes to 41, a key
that changes nothing (ESC) from 68 to 18. A 44-key editing session sends
21% fewer bytes at 24x80 (26% at 10x40); a frame whose status bar changes
costs about 1,900 cycles more.

### Scrolls with DL and IL

The rows that move as a whole (those below an edit that adds or removes
lines or rows, and the text rows when the view scrolls) go with DL
(`ESC[nM`) at the first row that moves and IL (`ESC[nL`) where the new
rows come in (`scroll_region_check`), each at column 1 of its row: up,
`ESC[<top>H ESC[nM ESC[<bottom-n+1>H ESC[nL`; down, the same with the two
rows swapped. No scroll region is set, and the status bar keeps its place
(the DL moves it up and the IL back), so its text on screen stays as
`status_send` knows it. IL leaves the cursor at column 1 of the first
row it opened, and `CUR_VALID` records it: the rows a view scroll, `dd`,
`o` or `p` exposes are drawn with no move of their own, and the paths
that also draw rows above the ones that move (`J`, a line that lost
rows) draw those first. The DL's move is left out when the cursor is
already there (`dd` from column 0). Against the region and SU/SD
(`ESC[<top>;<bottom>r ESC[nS ESC[r`, then a move), on a 10x40 screen:
`j` on the bottom row 56 bytes -> 54 (58 -> 55 at 24x80), `k` on the top
row 52 -> 51, `dd` 68 -> 62, `o` 65 -> 63, `P` 67 -> 65, Ctrl-D 77 -> 73,
`J` 82 -> 80, `D` on a 3-row line 81 -> 75. A frame that draws from
above the rows it opened sends 2 bytes more (the pair takes 14 bytes
where the region took 12): a line that gains a row, an Enter that splits
a line, an edit that moves the view. A move of the last text row alone
is still left to its callers, which rewrite that row: cheaper than
clearing it and moving back. Over the 94 scenarios of the audit's repaint bench
the bytes go from 31,302 to 31,225, and over about 20,000 random
sessions (typed ahead and paced, both builds) down 0.14%.

The rows IL opens are blank until the frame draws them, so the row loop
(`render_rows`) ends a short line or `~` there with no `ESC[K`: the
opened rows are the `SCROLL_N` rows from `SCROLL_ROW2`, which
`render_finish` resets. That saves 3 bytes per such row: `j` on the
bottom row 54 -> 51, Ctrl-D 73 -> 61, and `o` opens its empty row with
no text sent at all (63 -> 60).

### The command line runs within the `:` key

`:` reads its command line at the prompt within the key, as `/` and `?`
do, so the key's one frame shows what the command did. A frame for the
`:` alone would draw a status bar that the prompt erases at once: each
ex command now sends 45-49 bytes and 4,300-7,600 cycles less (`:5` on a
10x40 screen 108 bytes -> 61).

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
- `editor/insert.asm`: `insert_handle_key` writes to `BATCH_BUF` and copies
  into the buffer, so it needs gap-aware copy. The collection phase is
  unchanged.
- `editor/normal.asm`: Cursor movement may need to shift bytes across
  the gap, but the high-level logic stays the same.

**Incremental line adjustment with gap buffer:** With a gap buffer,
buf_adjust_lines_apply is no longer needed since insert/delete don't
shift the buffer. The line table just needs one new entry (for newline
insert) or one removed entry (for newline delete), plus the gap position
bookkeeping.

**Complexity:** This is a significant refactor. Plan in detail after
evaluating whether steps 1-3 provide sufficient performance.
