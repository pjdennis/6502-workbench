# Editor (6502 vi-like)

A vi-like text editor (~7,500 lines of 6502 assembly) that runs under the
project's 6502 emulator in console/ANSI mode.

## Architecture (files + roles)

### Entry point
- `editor.asm`: entry point, argument parsing, file load/save bootstrap,
  main loop, mode dispatch, memory layout constants, `TEXT_BUF`/`TEXT_LIMIT`
  definitions.  Includes all other source files via `.include`.

### Core systems
- `buffer.asm`: contiguous text storage with newline delimiters; line pointer
  table (`LINE_TBL`); insert/delete/shift operations; full rebuild and
  incremental line-table adjustment.
- `buffer_mem.asm`: page-optimized forward memory copy (`mem_copy_down`);
  `buf_shift_right_16` has its own backward (last byte first) copy loop.
- `undo_state.asm` / `undo.asm`: single-level undo/redo — types, zeropage
  state, and the shared 256-byte undo data page ($D700), plus the
  undo/redo handlers for every undoable operation.
- `render.asm`: core ANSI drawing — full-screen and current-line repaint
  (rows below scrolled when the line's row count changes, ICH/DCH row
  shifting), status bar, cursor positioning.
- `render_decide.asm`: snapshot-based render decision engine
  (`render_snapshot`/`render_decide`) and viewport scroll optimization.
- `render_scroll.asm`: scroll repaints (DL/IL) for line insert/delete and
  in-place range changes, the shared row renderer (`render_rows`), wrap
  math, cursor visibility.
- `input.asm`: key reader (`read_key`) with escape sequence parsing (arrow
  keys, Home/End/PgUp/PgDn/Delete, Ctrl+Left/Right; after an ESC it waits up
  to 100 ms through `io_wait` for the rest of a sequence), byte pushback, decoded
  key buffering, non-blocking peek (`key_peek`), blocking read (`get_key`),
  batch key counting.
- `terminal.asm`: ANSI escape sequence output (cursor move/hide/show, clear,
  reverse/normal video, string output, decimal output).
- `io.asm`: I/O abstraction layer — console mode (direct aliases) or
  `terminal_mode` (serial I/O with spin loops and DSR terminal size query).

### Mode handlers
- `normal.asm`: normal-mode main handler, dispatch tables (movement /
  editing / pending-combo), count prefix handling, x/X/dd, insert entry,
  o/O.
- `normal_move.asm`: normal-mode movement commands (h/l/j/k, 0/$, G/gg,
  Ctrl-F/B/D/U, search entry and n/N, mark set/jump, command mode entry)
  and the yank commands (yy/yw/yb/ye).  `^` and w/b/e are in `word.asm`.
- `normal_edit.asm`: normal-mode editing commands (paste, toggle case, join
  lines, substitute, change, replace).
- `normal_shift.asm`: indent/unindent (`>>`/`<<`) built on shared
  insert/remove-spaces cores (also used by range commands and undo),
  D/d$/y$/d0/y0 and the word operators (dw/db/de, cw/cb/ce),
  line-content helpers.
- `normal_util.asm`: shared utilities — generic key dispatcher, cursor/line
  helpers, vertical/horizontal movement and clamping, count prefix system,
  pair batching, line/char yank-and-delete and the x/X batched delete.
- `insert.asm`: insert-mode handler — printable chars, Enter, Backspace,
  Delete (forward), arrow keys, Home/End, PgUp/PgDn, word motions, batching
  of mixed Enter/BS/printable sequences, the undo record of the typing
  (a segment between cursor moves), and the copies ESC puts in after a
  count on `i`, `a`, `A`, `o` or `O`.
- `command.asm`: command-line mode — `:w`, `:q`, `:wq`, `:q!`, `:[N]`,
  `:marks`, range commands (`:[start],[end]d/y/>/<`).

### Feature modules
- `word.asm`: word motions — character classification
  (whitespace/word/punctuation), `w`/`b`/`e`/`^`, and the multi-line
  range routines of the word operators (dw/db/de, cw/cb/ce, yw/yb/ye).
- `yank.asm`: 4KB yank/paste buffer ($E000-$EFFF) — line yank and character
  yank types, multi-paste (Np).
- `search.asm`: forward (`/`) and backward (`?`) literal string search,
  wrap-around, pattern reuse with empty search, `n`/`N` repeat.
- `mark.asm`: 26 marks (a-z) stored as 16-bit line numbers, set/get/init,
  `:marks` display, automatic adjustment on insert/delete.

### Shared includes
- `17/environment.asm`: emulator I/O port definitions (shared with assembler).
- `17/macros.asm`: 16-bit macros (`SET16`, `LDAX16`, `STAX16`, etc.).
- `macros.asm`: editor-only macros (`ADDA16`, `PRINT_STR`); `17/macros.asm`
  is shared with the assembler.
- `zp.asm`: every editor zero-page variable, grouped by owning module and
  included before any code, so all zero-page references are backward ones
  (asm17 assembles a forward reference as absolute: one byte and one
  cycle more).

### Standalone demos (not part of the editor)
- `clock.asm`: HH:MM:SS clock display demo.
- `hello.asm`: terminal test program showing terminal size and key codes.

## Control flow

1. `editor_main` (in `editor.asm`) clears zero page (all state starts at 0),
   takes the file name from argv (`[No Name]` if none), and loads the file
   via `buf_load_file`; a missing or empty file starts as one empty line,
   which `EMPTY_BUF` marks as no lines (vim's ML_EMPTY: written as no
   bytes).
2. If the file is truncated, `READONLY` is set.
3. `render_init` gets the terminal size (a DSR query in the terminal build;
   keys typed before the terminal's reply arrives are dropped),
   `yank_init` and `mark_init` set up their state, and `render_screen` draws
   the first screen.  A truncated file then shows its warning.
4. Main loop:
   - Reset the handler's render inputs (`RENDER_FLAG` = 0, whole-line
     repaint, no ICH/DCH hint, no pre-computed rows).
   - Poll with `key_peek`.  When a key is ready, note the cursor
     line's screen rows (`PREV_LINE_ROWS`), `render_snapshot` (VIEW_TOP,
     VIEW_TOP_WRAP, line count, buf end), `get_key` reads the key (decoded
     by `read_key`), and it is dispatched to `normal_handle_key` or
     `insert_handle_key`.  `:`, `/` and `?` read their line at a prompt on
     the status row within the key (`read_line`), so the key's frame shows
     what the command did.
   - `CMD_QUIT` exits.  (The first key of a two-key combo (`dd`, `dw`,
     `gg`, ...) handles its second key at once if it has already arrived,
     so the pending key gets no frame of its own.)
   - `ensure_cursor_visible` moves the viewport if needed, as vim's does
     with 'scrolloff' 0 but for a far jump (the view shows whole lines
     from its top line and the cursor line in full; only a line taller
     than the screen starts above the view, `VIEW_TOP_WRAP`), then
     `render_decide` compares post-handler state against the snapshot and
     the handler's `RENDER_FLAG` (contract table in `render_decide.asm`):
     - `RENDER_FLAG` = `$FF` → full screen redraw.
     - Viewport moved → scroll the text area and draw the exposed rows
       (all of them for a move that fills it).  An edit rides along: when
       the view moved down (an `o`, Enter, `p` or `J` on the bottom row,
       typing past it) the rows from its first change on are drawn, as
       the rows above it keep their place in the scroll; when it moved
       up, the cursor line from its change point.  Full redraw for
       `RF_RANGE`, a first change on the top row or above the view, and
       on a move up for a line count change or an edited line that starts
       above the view or changed height above the status bar.
     - Line count changed → for the line insert, join and delete flags
       (`RF_INS`–`RF_DEL`) the lines that changed are drawn as one block
       from their first change, with the rows below moved (a delete
       draws only the rows that come in), else full redraw.
     - BUF_END changed or `RENDER_FLAG` set → current line redraw (rows
       below scrolled if its row count changed), or range redraw
       (`RF_RANGE`).
     - Nothing changed → status bar + cursor repositioning only; a key
       that changed nothing on the screen (ESC, an unmapped key, h at
       column 0, a yank) sends nothing at all.
   - Console build: the editor exits when input ends (`con_ready` returns
     `CON_EOF`): when idle, and in `get_key`, so also in a `:` or `/`
     prompt. Scripted and test runs need no `:q`.

## Data model & invariants

- **Text buffer**: `TEXT_BUF` (page-aligned after code), contiguous bytes,
  newline-delimited.  Always ends with a newline; empty buffer is one newline
  (with no lines, `EMPTY_BUF`, it is written as no bytes).
  `TEXT_BUF` floats automatically as code grows:
  `TEXT_BUF = _code_end + $00FF >> $08 << $08`.
- **Line table**: `LINE_TBL = $D800`, 16-bit pointers to each line start,
  then one holding the end of the text (`BUF_END16`): a line's length is
  the gap between its entry and the next, less the newline, found without
  a scan (`buf_get_line_len`).  The table and `LINE_COUNT16` are maintained
  by `buf_rebuild_lines` (after newline edits: it scans from the start of
  the cursor line on, the first line an edit changes) and
  `buf_adjust_lines_apply` (single-line edits without newlines), which
  both keep the end entry.
  Max 1023 lines (`MAX_LINES = $03FF`; the table has room for 1024 entries,
  the last for the end of the text).  A longer file loads truncated and read-only
  (`buf_rebuild_lines` cuts it), and every edit that would add lines
  past the limit checks first (`check_line_room`) and reports "Buffer
  full" without changing anything.
- **Buffer limits**: `TEXT_LIMIT` is conditionally defined at compile-time:
  - Normal build: `$D600` (buffer extends from TEXT_BUF up to BATCH_BUF)
  - Small buffer build (`define:small_buffer`): `TEXT_BUF + $0100` (256 bytes,
    for testing)
- **Self-editability**: every `editor/*.asm` source file must fit the text
  buffer and `MAX_LINES` so the editor can edit its own source (guarded by
  the test suite).
- **Editor state**: `CURSOR_ROW`, `CURSOR_COL16` (16-bit), `VIEW_TOP16`,
  `FILE_LINE16`, `MODE`, `MODIFIED`, `READONLY` live in zero page (all
  zero-page variables are declared in `zp.asm`).
  `FILE_LINE16` is the authoritative current line number; `CURSOR_ROW` is
  derived from it and `VIEW_TOP16`.
- **Read-only mode**: set if file load truncates (the text buffer or the
  line table is full); edit keys are ignored and `:w` / `:wq` are blocked.

## Memory layout

| Address | Size | Purpose |
|---------|------|---------|
| `$0000-$00FF` | 256 B | Zero page variables |
| `$0100-$01FF` | 256 B | 6502 stack |
| `$0200-$027F` | 128 B | Search pattern buffer (`SEARCH_BUF`; a pattern takes up to 127 and its null) |
| `$0280-$02FF` | 128 B | Unused (`FNAME_PTR16` points at the file name where the emulator keeps it) |
| `$0300-$037F` | 128 B | Command buffer (`CMD_BUF`) |
| `$0380-$03FF` | 128 B | Status bar text (`STATUS_SHADOW`) |
| `$0400+` | Variable | Editor code (loads here) |
| `TEXT_BUF` | Variable | Text buffer (page-aligned after code, up to `$D5FF`) |
| `$D600-$D61F` | 32 B | Batch insert staging buffer (`BATCH_BUF`) |
| `$D620-$D653` | 52 B | Mark table (`MARK_TBL`), 26 marks x 2 bytes |
| `$D6A0-$D6D3` | 52 B | The marks u puts back (`MARK_SAVE`: `mark_save`, `mark_restore`) |
| `$D700-$D7FF` | 256 B | Undo data page (`UNDO_DATA_BUF`) |
| `$D800-$DFFF` | 2 KB | Line pointer table (`LINE_TBL`), 2 bytes/entry |
| `$E000-$EFFF` | 4 KB | Yank buffer (`YANK_BUF`) |
| `$F000+` | | Emulator I/O |

## Key bindings

### Normal mode — movement

| Key | Action |
|-----|--------|
| `h` / Left | Move left (with count) |
| `l` / Right | Move right (with count) |
| Space / Backspace | Move right / left as `l` and `h`, on over line ends (with count; vim's 'whichwrap' b,s) |
| `j` / Down | Move down (with count) |
| `k` / Up | Move up (with count) |
| `0` / Home | Beginning of line |
| `$` / End | End of line (`[N]$`: of the line N - 1 below) |
| `^` | First non-blank character |
| `w` | Forward to next word start (with count) |
| `b` | Backward to previous word start (with count) |
| `e` | Forward to end of word (with count) |
| `G` | Go to last line; `[N]G` goes to line N |
| `gg` | Go to first line; `[N]gg` goes to line N |
| Ctrl-F / PgDn | Page down (with count) |
| Ctrl-B / PgUp | Page up (with count) |
| Ctrl-D / Ctrl-U | Half page down / up (a count is remembered) |
| Ctrl-Right | Word forward |
| Ctrl-Left | Word backward |
| `/` | Forward search |
| `?` | Backward search |
| `n` | Repeat search same direction (wraps) |
| `N` | Repeat search opposite direction |

### Normal mode — editing

| Key | Action |
|-----|--------|
| `i` | Insert at cursor (with count: ESC types the text count times, as vim) |
| `a` | Insert after cursor (with count) |
| `A` | Insert at end of line (with count) |
| `o` | Open line below (with count: count lines of the text) |
| `O` | Open line above (with count) |
| `x` / Delete | Delete character at cursor (with count, yanks) |
| `X` | Delete character before cursor (with count, yanks) |
| `D` | Delete to end of line (yanks) |
| `dd` | Delete line (with count, yanks) |
| `dw` | Delete word forward (with count, yanks) |
| `db` | Delete word backward (with count, yanks) |
| `cc` | Change line (with count, yanks, enters insert) |
| `cw` | Change word forward (with count, yanks, enters insert) |
| `cb` | Change word backward (with count, yanks, enters insert) |
| `C` | Change to end of line (yanks, enters insert) |
| `s` | Substitute character(s) (with count, yanks, enters insert) |
| `S` | Substitute line (alias for cc) |
| `r` | Replace character (with count; `r<Enter>` splits the line) |
| `~` | Toggle case (with count, advances cursor) |
| `J` | Join lines (with count) |
| `>>` | Indent line by 2 spaces (with count for multi-line) |
| `<<` | Unindent line by up to 2 spaces (with count) |
| `yy` | Yank line (with count) |
| `yw` | Yank word forward (with count, character yank) |
| `yb` | Yank word backward (with count, character yank) |
| `p` | Paste below/after cursor (with count) |
| `P` | Paste above/before cursor (with count) |
| `u` | Undo last edit / redo (single-level toggle; covers deletes, joins, pastes, `r`, `~`, `>>`, `<<`, range deletes and shifts, and text typed in insert mode, a stretch between cursor moves at a time, with the line `o` or `O` opened for it; the change commands only when ESC follows with no text typed, because typing after them clears the undo record) |

### Normal mode — marks

| Key | Action |
|-----|--------|
| `ma`–`mz` | Set mark |
| `'a`–`'z` | Jump to mark |

### Normal mode — other

| Key | Action |
|-----|--------|
| `1`–`9` | Start count prefix; `0`–`9` continues (a digit is ignored once the count is 1000 or more, so counts reach at most 9999) |
| `:` | Enter command mode |
| ESC | Clear count / pending key |

### Insert mode

| Key | Action |
|-----|--------|
| Printable chars | Insert text (batched, up to 32 chars) |
| Enter | Insert newline (batched) |
| Backspace | Delete backward (batched, including join-line batching) |
| Delete | Delete forward (batched) |
| Arrow keys | Navigate |
| Home / End | Beginning / end of line |
| PgUp / PgDn | Page up / down |
| Ctrl-Left / Ctrl-Right | Word backward / forward |
| ESC | Return to normal mode (cursor moves back one per vi convention) |

### Command mode

| Command | Action |
|---------|--------|
| `:w` | Save |
| `:q` | Quit (warns if modified) |
| `:wq` | Save and quit |
| `:q!` | Force quit |
| `:[N]` | Go to line N (1-based) |
| `:marks` | Display all set marks, a screen at a time (`-- More --`; `q` ends the list) |
| `:[start],[end]d` | Delete range |
| `:[start],[end]y` | Yank range |
| `:[start],[end]>` | Indent range |
| `:[start],[end]<` | Unindent range |
| `:>` / `:<` | Indent / unindent current line |

Range positions can be: decimal number (1-based), `'a` (mark), or `.`
(current line).

## Yank buffer

- 4 KB at $E000-$EFFF.
- Two types: **line yank** (from dd, yy, cc, range commands) and **character
  yank** (from x, D, dw, db, yw, yb, cw, cb, s, C).
- A yank, delete or change that does not fit is refused with "Yank buffer
  full": the text, the yank buffer and undo stay as they were.
- Line paste (`p`/`P`): inserts whole lines below/above.
- Character paste: inserts inline after/before cursor.

## Rendering + input

- Uses ANSI escape sequences via `terminal.asm` helpers (cursor move, clear
  line, reverse video status bar).
- Long lines wrap across multiple screen rows (vi-style), up to 255 rows
  per line: wrap rows (`WRAP_QUOT`, `VIEW_TOP_WRAP`, `RENDER_WRAP`) and row
  counts are bytes, and `div_mod_screen_cols_16` caps its quotient (and
  `line_screen_rows` its count) at 255.  Text past a line's 255th row
  (255 x `SCREEN_COLS` characters) is stored and saved but not displayed
  correctly.
- Lines past EOF shown as `~` (tilde).
- Tabs shown as `>`, other control characters, DEL and non-ASCII bytes as
  `?`, both in reverse video.
- Rows are drawn left to right, and only the first row a frame draws gets
  a cursor move: the row after one cleared to its end (`ESC[K`) is reached
  with CR LF, and a wrapped line's continuation rows by the terminal's
  auto-wrap (see Terminal requirements).  A row after one that ended its
  line exactly at the right edge gets a move too, as terminals differ in
  where they leave the cursor then.
- A frame's first move is left out when the last frame left the cursor
  there (`CUR_VALID`), or sent as a backspace when it is one column to the
  left; so is a move to the row an IL or DL of the frame's scroll left
  the cursor on.
- Rows that move as a whole (below an edit that adds or removes rows, or
  all of them when the view scrolls) go with DL and IL (see Terminal
  requirements).  The rows IL opens are blank, so a short line or `~`
  drawn there gets no `ESC[K`.
- The screen is at most 255 rows by 255 columns: a bigger terminal is used
  as 255 (the terminal build asks for the cursor at 255;255 and reads back
  where it went; the emulator caps the console build's size ports). On a
  terminal wider than 255 columns, lines longer than 255 characters still
  display wrongly, since the terminal does not wrap them at column 255.
- Status bar shows: filename, `[RO]`, `[+]`, mode, count/pending, line,col,
  total lines.  It stops one column short of the right edge (a character
  in the bottom-right cell followed by one more would scroll the screen),
  and a frame sends only the part that changed (`status_build` /
  `status_send`, with the text kept in `STATUS_SHADOW`).  Messages,
  prompts and the `:` / `/` echo are cut off the same way (`text_putc`),
  and the prompts take no more keys than fit.
- `input.asm` normalizes backspace and parses ESC sequences to high-bit key
  codes (`KEY_UP=$80`, `KEY_DOWN=$81`, etc.).
- Snapshot-based render optimization minimizes redraw work per keystroke.

### Terminal requirements

The editor needs an ANSI terminal such as xterm (or a serial terminal
program emulating one) that handles the escape sequences below and behaves
as a VT102 does by default:

- Escape sequences: cursor position (`ESC[<row>;<col>H`), erase to the end
  of the line (`ESC[K`), clear screen (`ESC[2J`), reverse and normal video
  (`ESC[7m`, `ESC[m`), cursor hide and show (`ESC[?25l`, `ESC[?25h`),
  insert and delete lines (`ESC[<n>L`, `ESC[<n>M`), insert and delete
  characters (`ESC[<n>@`, `ESC[<n>P`), the scroll region reset (`ESC[r`,
  sent at exit), and in the terminal build the cursor position report
  (`ESC[6n`).  A parameter equal to its default is left out, so a missing
  one must take its default: `ESC[H` is row 1, column 1, `ESC[5H` column 1
  of row 5, `ESC[M` one line, `ESC[P` one character.
- Insert and delete line (IL, DL): rows that move as a whole (the rows
  below an edit that adds or removes lines or rows, and the text rows when
  the view scrolls) are moved with DL at the first row that moves and IL
  where the new rows come in, each sent at column 1 of its row, with no
  scroll region set: the status bar keeps its place (it moves up with a DL
  and back with the IL after it).  IL and DL came with the VT102 (a plain
  VT100 has neither), and every terminal that emulates a VT102 or later
  has them: xterm and the terminals that follow it (GNOME Terminal and
  others built on VTE, Konsole, iTerm2, Windows Terminal), the Linux
  console, PuTTY, Tera Term, minicom, screen and tmux.
- Plain CR and LF: CR moves to column 1 of the same row, and LF one row
  down in the same column.  A row the row loop has finished (ended with
  `ESC[K`) is followed by CR LF to reach the next one, so a terminal that
  adds a LF to each CR it receives draws those rows a row too low and
  scrolls the screen.  Serial terminal programs have that as an option,
  off by default, which must stay off: PuTTY's "Implicit LF in every CR",
  Tera Term's receive new-line "CR+LF" (use "CR"), minicom's "Add
  linefeed".  Adding a CR to each LF (new-line mode) does no harm: every
  LF follows a CR.  No LF is sent from the last text row, so none scrolls
  the screen.
- Backspace moves the cursor one column left (a frame that starts one
  column left of the cursor, as X and a backspace in insert mode do, uses
  it).
- Auto-wrap: a wrapped line's continuation rows are reached by writing
  past the right edge, with no cursor move.  Terminals that wrap at once
  (the emulator's console) and those that wrap only when the next
  character comes (a VT100, xterm) both work: nothing that moves the
  cursor comes between a full row and the next character of its line (at
  most a switch to reverse video, for a control character).  The status
  bar stops one column short of the right edge, so the bottom-right cell
  is never written.

## Performance

- **Batching**: the editor aggressively batches buffered input:
  - Printable chars in insert mode: up to 32 chars (mixed Enter/BS/printable)
    in one batch.
  - Backspace/Delete in insert mode: count and delete multiple at once.
  - Enter in insert mode: batch multiple newline insertions.
  - Join-lines (BS at column 0): batch multiple joins.
  - Movement keys: batch identical keys (e.g., multiple j/k/h/l).
  - Two-key combos dd, >> and <<: count additional pairs.
  - dw/db/de pairs: run each press separately (N presses can differ from a
    count of N at line ends), then render once.
- **Page-optimized memory ops**: byte shifting uses inner Y-indexed loops
  processing 256 bytes per page.
- **Incremental line table updates**: single-char edits without newlines use
  `buf_adjust_lines_apply` instead of full rebuild.
- **Range repaint**: `>>`/`<<`/range shifts and their undo repaint only the
  affected screen rows; wrap growth/shrink scrolls the region below instead
  of a full repaint. No-op shifts repaint nothing.
- **Direct echo**: `r` and `~` echo changed chars in place (no repaint) up
  to the wrap-row boundary, deferring the remainder to a partial line
  render.
- **Batching vs undo**: batching merges execution only; undo always behaves
  as if the keys were processed one at a time (u undoes the last one).

## Conditional compilation

| Define | Effect |
|--------|--------|
| `define:small_buffer` | Reduces `TEXT_LIMIT` to 256 bytes (for testing truncation/read-only) |
| `define:terminal_mode` | Switches to serial I/O with spin loops and DSR terminal size query |

## Testing

- `editor/tests/editor_tests.py` assembles the editor (using `17/out/asm.out`
  via the emulator) and runs it under `../../emulator/emulator.out`, feeding
  keystroke byte streams and verifying saved file contents and screen state.
- `editor/tests/ansi_screen.py` is a virtual terminal that processes ANSI
  escape sequences into a screen buffer for screen-state assertions.
- Bounds checking tests build `editor_small.out` with `define:small_buffer` to
  force truncation/read-only scenarios.
- On success, copies the builds to `editor/out/editor_stable.out` (used by
  `editor-fast.sh` and `editor-slow-console.sh`) and
  `editor/out/editor_terminal_stable.out` (used by `editor.sh` and the
  `editor-terminal-*.sh` scripts).

### Quick commands
```bash
# Run tests (from toolchain/asm2):
python3 editor/tests/editor_tests.py -q

# Run editor (terminal build, 19200 baud, 2 MHz):
./editor.sh <file>
```

## Build/run

```bash
# Assemble (release):
../../emulator/emulator.out 17/out/asm.out editor/editor.asm editor/out/editor.out

# Assemble (small buffer):
../../emulator/emulator.out 17/out/asm.out editor/editor.asm editor/out/editor_small.out define:small_buffer

# Assemble (terminal mode):
../../emulator/emulator.out 17/out/asm.out editor/editor.asm editor/out/editor_terminal.out define:terminal_mode

# Run (console):
../../emulator/emulator.out editor/out/editor.out --load 0400 --console <file>

# Shortcuts: editor.sh runs editor_terminal_stable.out (--terminal
# --baud 19200 --mhz 2); editor-fast.sh runs editor_stable.out (--console)
./editor.sh <file>
```

## Tips for LLMs making changes

- Any edit that changes buffer contents must update the line table
  (`buf_rebuild_lines` if newlines changed, with `FILE_LINE16` on the first
  line the edit changed, or `buf_adjust_lines_apply` for edits within one
  line) and set `MODIFIED`.
- Keep the "always newline-terminated buffer" invariant intact.
- When moving between lines, clamp `CURSOR_COL` to the current line length.
- Normal-mode edit keys should be gated by `READONLY`.
- `FILE_LINE16` is the authoritative current line; `CURSOR_ROW` is derived
  from it, not the other way around.
- Dispatch tables use 3-byte entries `[key, handler_lo, handler_hi]` for
  simple keys and 5-byte entries `[key1, key2, flags, handler_lo, handler_hi]`
  for two-key combos (key2=0 means wildcard).
- Yank operations must set `YANK_TYPE` (line vs char) — paste behavior
  depends on it.
