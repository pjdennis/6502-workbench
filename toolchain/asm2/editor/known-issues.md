# Known issues

What the audit of the editor (September 2026) left open that is not a
difference from vim kept on purpose: defects, and repaint bytes and CPU
cycles that could come down. Each entry has a repro and an estimate of
its code bytes (*measured* where a sandbox prototype was built). The
differences from vim are listed in `vi-compatibility-changes`, and the
larger ones are planned, with their costs, in `vim-gaps.md`; they are not
repeated here (the last section has the estimates for the smaller ones).

Screens are rows x columns; keys are as typed (`<CR>` is Enter). When
this file was added the console build was 13,227 bytes and the terminal
build 13,305, both with `TEXT_BUF` at $3800: 85 and 7 bytes spare, so
any fix here costs the terminal build a page of text buffer unless
something else shrinks.

## Defects

### Typed-ahead keys and the view

Keys typed one at a time (as vim takes them) each move the view as they
need; a batch of keys typed ahead (an insert batch, or h, l, Space and
Backspace presses taken as one count) moves it once, at the end, so the
view can end elsewhere:

- **Enters, then a Delete that shrinks the new line.** 4x10, 'line 10
  text', `a<CR><CR>`, Delete, Esc: one at a time the second Enter scrolls
  the view ('ine 10 text' takes two rows), and the Delete leaves it there
  ('', 'ne 10 text', '~'); typed ahead the batch ends with lines that
  fit, and the view stays ('l', '', 'ne 10 text'). Ending a batch at a
  Delete after an Enter it typed, as it ends at a Backspace of one:
  about 10 bytes (estimate). A Backspace of chars typed after an Enter
  can do the same and would need more.
- **A line taller than the screen** keeps its place while its rows to
  the cursor fit (vim's skipcol), so its view depends on the rows the
  cursor went through. 4x10, 41 x's, an empty line and 'l', keys `G`,
  `0k`, Backspace, Backspace: one at a time the first Backspace goes to
  the line's fifth row and the second back to its fourth, with the line
  shown from its third row; typed ahead (one move to the fourth row) it
  shows from its second. 4x10, 39 x's, `G`, `0k`, `A`, Backspace twice,
  `ab`, `x`, Backspace, Esc: the same ('x' took the cursor to a fifth
  row). Ending a batch, or updating the view per press, when the cursor
  line is taller than the text rows: about 15 to 30 bytes (estimate).

Of 2,000 sessions of insert keys typed at the top rows after `G` and `k`
(the audit's work/wrapup/pacedtop.py), 7 end on another view typed ahead
than one at a time: 3 of the first kind, 4 of the second.

### The terminal's size reply

The terminal build asks for the size at startup and takes the first
`ESC[rows;colsR` it reads. A reply of one row is taken for a key
(xterm's F3 with a modifier, `ESC[1;2R`), so a terminal of one row
waits at startup for a reply that does not come. A key typed before the
reply that has the reply's shape with more rows is still taken as the
size; no common key has it. Taking only a reply that comes within a few
milliseconds of the query (`io_wait`) would settle both: about 15 to 25
bytes (estimate).

### Narrow screens

The `:` and `/` prompts take the screen width less 2 characters
(`vi-compatibility-changes`, Command line), so on 3 columns `:wq` is
taken as `:w`, and on 2 columns no command fits. With 4 columns or more
`:q!` and `:wq` fit.

### Lines of more than 255 screen rows

A line wraps across at most 255 screen rows (HELP, Display): text past
its 255th row is kept and saved but not displayed correctly, and with
the cursor there the view is wrong. 16-bit wrap rows and row counts in
the render code would lift it (the audit's D049; not estimated).

## Repaint bytes

The byte counts are frames of the final build: the bytes sent for one
key, from after the frame before.

- **An edit that moves the view up rewrites rows it shifted.** 10x40,
  104 a's and 'line 1'..'line 11', keys `5lx8Gu`: the u frame (176 bytes)
  scrolls, shifts the three rows of the long line with ICH (24 bytes),
  then writes all three rows again. render_line_shift would have to
  advance its per-row state without output for rows the exposed range
  covers: about 10 bytes.
- **dd or :d of the only line when it is empty** (a file of one empty
  line) sends ESC[K for the row, which does not change: 3 bytes of a
  47-byte frame. The RF_DEL path would have to tell that nothing moved on
  screen: about 8 bytes, more than it saves.
- **Typed-ahead pp** is drawn as an Enter that split the line the copies
  follow, from its end, and sends an ESC[K there (10x40, 'Line 1'..'Line
  15', `jjjyypp`: 87 bytes, 9 of them for that ESC[K and its move). With
  a count (`3pp`) the frame is a full redraw.
- **Scrolls that start their drawing above the rows they open** (a line
  that gains a row, an Enter that splits a line, the undo of J or of a
  split) send the DL/IL pair's cursor move again: 10x40, 'L1'..'L14',
  `4jA<CR><Esc>`: the Enter frame is 60 bytes; `4jli<CR>` 72. Keeping a
  scroll region for those callers measured about 30 bytes of code for
  0.03% of the fuzz's bytes. For one Enter at the end of a line
  mid-screen, sending the status bar before the scroll ends the frame
  where IL left the cursor: 60 -> 56 bytes, +13 bytes of code, -712 bytes
  over 9,000 fuzz sessions (*measured*; the audit's
  work/phase7e/src_ent).
- **A row IL opened is reached and then gets nothing**: the row loop
  moves to an empty line's row before it knows the row needs no ESC[K
  (2 to 5 bytes). 24x80, 40 lines of 48 characters, `22jA<CR><Esc>`: the
  Enter frame (75 bytes) ends the split line with ESC[K CR LF and then
  goes to the status bar. Skipping such rows in the opened range: about
  10 to 15 bytes.
- **Scrolls that keep one short row** on screens of 2 to 4 text rows:
  the DL/IL pair can cost about what redrawing the kept row does (3x10,
  'x' and five empty lines, `Go<Esc>`: the o frame 43 bytes, the first
  full frame 44). Not measured against a forced full redraw.
- **The redo of r<Enter> on a line above the view** (u, a move that
  scrolls the line off the top, u again) is drawn in full: the lines at
  the top of the view are others after it. A scroll down by the new
  line's rows and a draw of the rows it opens would do; the case is rare.

## CPU

### Enter and joins in insert mode rebuild the line table to the end

A batch that adds or removes line breaks rebuilds the line table from
the change to the end of the text: at the top of a 36 KB file (900
lines of 41 characters, 24x80) `i<CR><Esc>` takes 1,182,825 cycles more
than `i<Esc>`, and a Backspace joining line 2 onto line 1 about as many.
Splicing the table in place (one routine for every rebuild caller,
handling the lines deleted and inserted and the line limit) would take
about a third off (the audit's P014: 80 to 120 bytes, estimate).

### The cursor row is worked out again every key

ensure_cursor_visible walks up from the cursor line to the top line
every key, so a key costs more the lower the cursor is: `l` takes 5,717
cycles on the top row of a screen of short lines and 10,905 on the
bottom row at 24x80, 62,127 at 255x80. A cache of the cursor row is
unsafe with the obvious keys (a batch that adds and removes a line break
keeps them all); a safe one would cost 60 to 85 bytes, against the
serial output a key sends anyway (the audit's P055: not recommended).

### Loops across a page

A taken branch to another page costs one cycle more, so where a loop
lands matters, and any change to the code before it can move it.
Crossing when this file was added, none per drawn character or per text
byte (the loop's routine, and what a crossing costs):

- console build: read_key's drain of an unknown CSI sequence (per
  byte), mul_by_count (per count digit), normal_page_down (per page),
  shift_line_start and remove_spaces_core (per line of `>>` and `<<`),
  marks_display (per mark listed);
- terminal build: query_terminal_size (at startup), read_key's CSI
  drain, render_rows' step to a wrapped line's next row (per row),
  render_decide's walks (per line a view move walks), shift_row (per
  rewritten row), normal_space's steps (per step of a count),
  insert_spaces_core (per line of `>>`), insert_handle_key's collection
  loop (per typed-ahead key in insert mode) and mark_init (once).

add45ef moved off those per text byte and those every key runs
(dispatch_key's table scan, count_pending_key's). The collection loop's
branch is taken only for a key typed ahead, and render_rows' step only
for a wrapped line's next row; they would need their routines 3 to 8
bytes later in both builds (insert_handle_key) and 11 bytes later or 16
earlier in the terminal build (render_rows).
An assembly-time check (a macro that fails when a branch's target and
the next instruction are on different pages) would keep the hot ones
off.

## Test harness and emulator notes

- In the console build a `--pace-mask` pause ends on a con_ready or
  wait_ready poll, not on a blocking read (read_b): a key read by a
  blocking read right after a paced key comes from the file, so an ESC
  wait inside the pause times out and a Delete there splits into ESC and
  `[3~`. The blocking reads left are the `:` and `/` prompts and
  `:marks`; paced checks that pause inside those should use terminal
  mode.
- The render oracle (the screen after keys K equals the screen after K
  and a forced full redraw) needs `:marks<CR>q`, not `:marks<CR>` and a
  space: `:marks` pages with "-- More --" when more marks are set than
  fit, and q ends the list there and dismisses it otherwise. Type Esc
  Esc before it to leave any pending key or message.
- Terminal runs never exit at the end of their input: a test whose keys
  do not quit (a pending `d` takes the `:` of `:q!`, or the prompt on a
  screen of 2 columns cannot hold it) times out.
- The emulator prints no cycle count in `--terminal` (and `--console`)
  mode, and `--cycle-cap` does not apply there: a terminal run that
  loops needs `timeout`. The audit's terminal cycle counts came from a
  copy of the emulator that prints them.

## Differences from vim

All are listed in `vi-compatibility-changes`; `vim-gaps.md` has the
larger ones (`:w {file}`, J's leading blanks, the search messages,
Ctrl-F and Ctrl-B over long lines, the far-jump view and '@' rows, j and
k over Tabs, the counts on i, a, A, I, o and O) with their costs. The
smaller ones, with estimates from the routines they would change:

| Difference (`vi-compatibility-changes`) | Estimate |
|---|---|
| Counts over 255: w, b and e | about +10 bytes |
| Counts over 255: x and X (a range past 255 can overflow the yank buffer) | about +25 |
| Counts over 255: ~ (a 16-bit undo span) | about +20 |
| Counts over 255: r and J | limited by the 256-byte undo page |
| Reports: ">ed" and "<ed" for shifts | about +25 |
| Reports: "3 more lines" after p and P | about +35 |
| Reports: "3 fewer lines" and "3 lines yanked" after charwise ones | about +25 |
| Reports: "--No lines in buffer--" | about +30 |
| Marks: u deletes the marks of the lines it replaces | about +35 |
| Marks: Ctrl-R (u u) puts back the marks its undo deleted | about +9, and +3 per redo |
| Empty changes: dw on an empty last line | about +6 |
| Empty changes: C on an empty line yanks the empty text | about +8 |
| J with a count on the last line | not estimated |
| :N,M> and :N,M< end on the last changed line's column | not estimated: the shift cores would track it |
| The status bar shortens a long name from the left | not estimated (the audit's P004 note) |
