# Plan: ICH/DCH shifting for in-line edits

Use the terminal's Insert Character (`ESC[n@`, ICH) and Delete Character
(`ESC[nP`, DCH) controls so that an in-line edit shifts the existing text on
screen instead of resending everything after the edit point. Scope: insert
mode (typing, BS, DEL, including type-ahead batches) and normal-mode `x`,
`X` (new) and `D`.

VT100 compatibility is out of scope for now. ICH/DCH are always on (VT102
and later, xterm-alikes, Windows Terminal, PuTTY, minicom all support them).

## Where things stand

- **Batching exists.** `insert_batch` (`insert.asm`) collects up to
  `BATCH_MAX` (32) queued keys and reduces them to
  `[back N] [insert BATCH_BUF] [fwd N]`, then shifts the buffer once. Its
  fast path (no newlines involved) sets `RENDER_FROM_COL16 = c0`, the first
  changed column. `x` batches pending `x` keys the same way
  (`get_batched_count` + `batched_char_delete`).
- **The render rewrites the tail.** `render_current_line_and_status`
  (`render.asm`) redraws from `c0` to the end of the row, then every later
  wrap row of the line in full. At 300-9600 baud in the terminal build,
  typing near the start of a long line resends the whole line per batch.
- **Buffer bytes map 1:1 to screen cells.** Tab renders as a reverse `>`,
  unprintables as a reverse `?` (`render_line_chars`, `render_scroll.asm`),
  so a buffer shift of `net` bytes is a screen shift of `net` cells.
- **Interpreter support.** `tests/ansi_screen.py` handles `@` and `P`
  (step 1, done). The emulator's screen model (`emulator/console.c`) does
  not yet. It drives both redraw after Ctrl-Z/`fg` and the
  `--show-repaints` highlighting: the real terminal gets the editor's bytes
  directly, while the model tracks cells plus per-cell highlight state
  (`repaint_time`, `repaint_count`, `repaint_displayed`), and
  `repaint_overlay_update` re-sends cells from the model with a background
  color as highlights turn on and fade. A model that ignores ICH/DCH would
  put stale characters on screen and leave shifted highlights that never
  fade.
- **`X` is not implemented**; only `x` / Delete are bound (`normal.asm`).
- **`D` is already near-minimal.** It sets `RENDER_FROM_COL16` to the
  cursor, so the partial render writes nothing and emits `ESC[K`; if the
  line loses wrap rows, the rows-decreased path scrolls the rest up. Nothing
  remains to the right of the cursor to shift, so DCH brings no gain.

## Render contract

A handler that wants shifting sets two new zero-page variables alongside
`RENDER_FROM_COL16 = c0`:

- `SHIFT_NET` (signed byte): `insert_len - deleted_len`. `0` = no shift
  info (current behaviour).
- `SHIFT_WRITE` (byte): number of new cells to write starting at `c0`
  (`insert_len`; `0` for pure deletes).

`editor.asm`'s main loop resets both each iteration, next to
`RENDER_FROM_COL16`. Deltas are at most 255 cells: insert batches are
capped at 32, and `x` counts are capped at 255 by `get_batched_count`.

Callers:

| Handler | c0 | SHIFT_NET | SHIFT_WRITE |
|---|---|---|---|
| `insert_batch` fast path | `col - back` | `insert_len - back - fwd` | `insert_len` |
| `x` / Delete (count n, clamped to line) | cursor | `-n` | 0 |
| `X` (count n, clamped to col) | `col - n` | `-n` | 0 |

Type-ahead needs no extra work: a whole batch becomes one `SHIFT_NET`, so
each screen row gets at most one ICH/DCH.

## Screen algorithm

For each screen row `r` of the line, from the row holding `c0` to the
line's last row that is on screen (never the status row), with
`s = max(rowStart, c0)`:

- **`net > 0` (insert):** move to `s`, `ICH net`, then write new cells
  `[s, max(c0 + SHIFT_WRITE, s + net))`, clipped to the row. On later rows
  those first `net` cells are the characters pushed off the row above.
  Every other cell is already correct because ICH moved it. A row that
  did not exist before the edit is blank: skip the ICH and just write.
- **`net < 0` (delete, `d = -net`):** move to `s`, `DCH d`, then write
  `[s, c0 + SHIFT_WRITE)` plus the last `d` cells of the row, pulled up
  from the next row, stopping at the new end of the line. On the line's
  last row the blanks DCH leaves on the right are already correct.
- **`net = 0`:** overwrite `SHIFT_WRITE` cells only (existing partial
  render, cut short).
- **Cost check per row:** use the shift only when it saves more than the
  sequence costs (about 4-6 bytes). Otherwise, or if `|net|` is at least
  what is left of the row, rewrite from `s` as today.

When the line gains or loses screen rows, the existing scroll logic in
`render_current_line_and_status` opens or closes rows below the line
first; the per-row step replaces only its "render the cursor line from the
change point" part.

Example (40 columns, 3-row line, typing `AB` at column 5):
row 0 `ESC[1;6H ESC[2@ AB`; row 1 `ESC[2;1H ESC[2@` + the 2 carried
chars; row 2 likewise. About 30 bytes instead of about 115.

## Steps

Red, green, commit each step (tests and the code that passes them in the
same commit; refactors in their own commits).

1. **`AnsiScreen` ICH/DCH** (`tests/ansi_screen.py`). *Done.* Handle `@` and `P`:
   missing count means 1, the count is clamped to the rest of the row,
   per-cell attributes shift with the characters, pending wrap is
   cancelled, and shifted cells are not counted as written, so
   `expect_min_col` / `expect_max_col` keep measuring what was actually
   sent. Interpreter self-tests first.

2. **Emulator `console.c` ICH/DCH, including `--show-repaints`.** *Done.* Same
   semantics as step 1 in the C screen model, so redraw after
   suspend/resume stays correct. Highlighting rule: **shifting is not
   painting.** Only characters actually written light up, which is what
   makes the savings visible (typing one char mid-line lights one cell,
   not the rest of the line). Concretely, following the pattern of
   `console_scroll_region_up` / `down`:
   - shift `screen_cells`, `screen_attr` and all three highlight arrays
     together within the row, so an existing highlight travels with its
     character (a real terminal moves cell colors with ICH/DCH too) and
     fades out where it now is;
   - do not stamp or bump `repaint_time` / `repaint_count` for shifted
     cells;
   - zero the highlight state of freed cells (ICH blanks, DCH blanks at the
     right), matching the terminal, which shows them with no background
     because the overlay always resets colors after drawing.

   Tests in `emulator/tests/test_console.c` first: cell and attribute
   shifting (count defaults, clamping, dropped cells); with repaint
   tracking enabled, a shifted cell keeps its own highlight state at its
   new column, a cell that was never written stays unhighlighted after a
   shift, freed cells come out unhighlighted, and an ICH/DCH alone does not
   make the overlay emit anything new.

3. **`X` command (feature, existing render).** *Done.* Delete `count` characters
   before the cursor, clamped at column 0; the cursor moves left by the
   deleted count; yanks as a character yank and records undo like `x`;
   no-op at column 0; blocked in read-only mode. Build it on the `x` path
   (compute the backward range, move the cursor, then the shared
   yank/delete code), with batching of pending `X` keys like `x`. Update
   `HELP` and the editor `README.md` command table. Tests first: content, cursor, count,
   count past column 0, column 0 no-op, `p` after `X`, `u` after `X`,
   read-only.

4. **Refactor (no behaviour change, all existing tests pass unchanged).**
   - `terminal.asm`: merge `ansi_scroll_up` / `ansi_scroll_down` into one
     `ESC[` + count + final-byte emitter; add `ansi_insert_chars` and
     `ansi_delete_chars` on it.
   - `render.asm`: the same-count, rows-decreased and rows-increased
     branches of `render_current_line_and_status` each carry their own
     partial render. Extract one `render_line_from_change`.
   - `render_line_chars_from`: add a stop column so it can write exactly
     n cells.

5. **Single-row lines: insert mode, `x`, `X`.** Add `SHIFT_NET` /
   `SHIFT_WRITE`, set them from `insert_batch`'s fast path and from the
   `x` / `X` handlers, and use the per-row step in
   `render_line_from_change` when `SHIFT_NET != 0`. Failing tests first
   (10x40 screen, each with and without `deferred_wrap`):
   - one char typed mid-line: row correct, output contains `ESC[1@`, the
     frame writes only column `c0`;
   - type-ahead `ABC` in one batch: a single `ESC[3@`, writes only up to
     `c0 + 2`;
   - insert-mode BS and DEL mid-line: `ESC[1P`, no cells written after
     `c0`;
   - mixed batch (type 3, BS 1): one `ESC[2@`; type 1 + DEL 1: no ICH/DCH;
   - insert at end of line: no ICH;
   - `x`, `3x`, batched `xxx`, normal-mode Delete: one DCH of the total,
     nothing written;
   - `X`, `3X`: one DCH at `col - n`, nothing written;
   - `x` on the last char: the cell ends up blank.

6. **Wrapped lines, row count unchanged.** Tests: insert, BS, `x` and `X`
   in row 0 of a 3-row line; each later row gets its own ICH/DCH and
   writes only the carried cells (e.g. row 1 writes only `0..net-1`); a
   tab or unprintable carried across a row boundary keeps reverse video.

7. **Row count changes.** Tests: insert that pushes the line onto a new
   row (rows below scroll down intact; the new row holds exactly the
   carried chars); `x` / BS that removes a row (rows below scroll up
   intact); a line running past the bottom of the screen (nothing written
   into the status row); first row above the viewport (still a full
   repaint); line length an exact multiple of the width with the cursor at
   the end (the `PREV_LINE_FULL` edge in insert mode).

8. **`D` lock-in tests.** Assert that `D` mid-line writes no text cells
   (only `ESC[K` on the cursor row), and that `D` on a wrapped line clears
   the remainder and scrolls the rows below up without rewriting them. No
   code change expected; if a test fails, fix the render rather than the
   test.

9. **Cost check and cleanup.** Tests where rewriting is cheaper, so no
   ICH/DCH is emitted (short tail, large `|net|`). Remove duplication; add
   a "Completed" entry to `PERFORMANCE.md`.

Existing screen tests that assert which cells get rewritten in insert mode
or after `x` encode the old strategy. Review and update them one by one,
keeping the full screen contents asserted; no blanket rebaselining.

## Out of scope / follow-ups

- Batches containing newlines (Enter and line joins) already use the
  scroll paths.
- `d{motion}` within a line (`dw`, `de`, `db`, `d0`), `s`, character paste
  and undo/redo of character edits: once `render_line_from_change`
  exists, each only needs to set `SHIFT_NET` / `SHIFT_WRITE`.
- Optional VT100 fallback (a `define:no_ich` build that rewrites instead).
