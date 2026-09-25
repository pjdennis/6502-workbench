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
- `buffer_mem.asm`: page-optimized memory copy routines (`mem_copy_up`,
  `mem_copy_down`).
- `undo_state.asm` / `undo.asm`: single-level undo/redo — types, zeropage
  state, and the shared 256-byte undo data page ($D700), plus the
  undo/redo handlers for every undoable operation.
- `render.asm`: core ANSI drawing — full-screen render with line wrapping,
  status bar, cursor positioning, current-line repaint.
- `render_decide.asm`: snapshot-based render decision engine
  (`render_snapshot`/`render_decide`) and viewport scroll-region
  optimization.
- `render_scroll.asm`: scroll-region repaints for line insert/delete and
  in-place range changes, limited-row rendering, wrap math, cursor
  visibility.
- `input.asm`: console key reader, escape sequence parsing (arrow keys,
  Home/End/PgUp/PgDn/Delete, Ctrl+Left/Right), pushback, decoded key
  buffering, non-blocking polling, batch key counting.
- `terminal.asm`: ANSI escape sequence output (cursor move/hide/show, clear,
  reverse/normal video, string output, decimal output).
- `io.asm`: I/O abstraction layer — console mode (direct aliases) or
  `terminal_mode` (serial I/O with spin loops and DSR terminal size query).

### Mode handlers
- `normal.asm`: normal-mode main handler, dispatch tables (movement / editing /
  other / pending-combo), count prefix handling.
- `normal_move.asm`: normal-mode movement commands (h/l/j/k, 0/$, ^, w/b/e,
  G/gg, Ctrl-F/B, search entry, mark jump, command mode entry).
- `normal_edit.asm`: normal-mode editing commands (paste, toggle case, join
  lines, substitute, change, replace).
- `normal_shift.asm`: indent/unindent (`>>`/`<<`) built on shared
  insert/remove-spaces cores (also used by range commands and undo),
  dollar/word operator commands, line-content helpers.
- `normal_util.asm`: shared utilities — generic key dispatcher, cursor/line
  helpers, vertical/horizontal movement loops, count prefix system, pair
  batching.
- `insert.asm`: insert-mode handler — printable chars, Enter, Backspace,
  Delete (forward), arrow keys, Home/End, PgUp/PgDn, word motions, batching
  of mixed Enter/BS/printable sequences.
- `command.asm`: command-line mode — `:w`, `:q`, `:wq`, `:q!`, `:[N]`,
  `:marks`, range commands (`:[start],[end]d/y/>/<`).

### Feature modules
- `word.asm`: word motions — character classification
  (whitespace/word/punctuation), `w`/`b`/`e`/`^`, scan helpers for
  dw/db/cw/cb.
- `yank.asm`: 4KB yank/paste buffer ($E000-$EFFF) — line yank and character
  yank types, multi-paste (Np).
- `search.asm`: forward (`/`) and backward (`?`) literal string search,
  wrap-around, pattern reuse with empty search, `n`/`N` repeat.
- `mark.asm`: 26 marks (a-z) stored as 16-bit line numbers, set/get/init,
  `:marks` display, automatic adjustment on insert/delete.

### Shared includes
- `17/environment.asm`: emulator I/O port definitions (shared with assembler).
- `17/macros.asm`: 16-bit macros (`SET16`, `LDAX16`, `STAX16`, etc.).
- `17/to_decimal.asm`: decimal number formatting.

### Standalone demos (not part of the editor)
- `clock.asm`: HH:MM:SS clock display demo.
- `hello.asm`: terminal test program showing terminal size and key codes.

## Control flow

1. `editor_main` (in `editor.asm`) parses argv, opens file if present, and
   loads buffer via `buf_load_file`.
2. If the file is truncated, `READONLY` is set and a warning is shown.
3. `render_init` detects terminal size + initial `render_screen`.
4. Main loop:
   - `render_snapshot` captures current state (VIEW_TOP, line count, buf end).
   - If `MODE == MODE_COMMAND`, run `command_handle` (does its own input).
   - Otherwise `read_key` and dispatch to `normal_handle_key` or
     `insert_handle_key`.
   - `render_decide` compares post-handler state against snapshot:
     - VIEW_TOP or line count changed → full screen redraw.
     - BUF_END changed → current line + status bar redraw.
     - Nothing changed → status bar + cursor repositioning only.
   - `CMD_QUIT` exits.
   - EOT (`$04`) exits early for scripted/test mode.

## Data model & invariants

- **Text buffer**: `TEXT_BUF` (page-aligned after code), contiguous bytes,
  newline-delimited.  Always ends with a newline; empty buffer is one newline.
  `TEXT_BUF` floats automatically as code grows:
  `TEXT_BUF = _code_end + $00FF >> $08 << $08`.
- **Line table**: `LINE_TBL = $D800`, 16-bit pointers to each line start.
  `LINE_COUNT16` is maintained by `buf_rebuild_lines` (after newline edits)
  and `buf_adjust_lines_inc/dec` (single-char edits without newlines).
  Max 1023 lines (`MAX_LINES = $03FF`).
- **Buffer limits**: `TEXT_LIMIT` is conditionally defined at compile-time:
  - Normal build: `$D600` (buffer extends from TEXT_BUF up to BATCH_BUF)
  - Small buffer build (`define:small_buffer`): `TEXT_BUF + $0100` (256 bytes,
    for testing)
- **Self-editability**: every `editor/*.asm` source file must fit the text
  buffer and `MAX_LINES` so the editor can edit its own source (guarded by
  the test suite).
- **Editor state**: `CURSOR_ROW`, `CURSOR_COL16` (16-bit), `VIEW_TOP16`,
  `FILE_LINE16`, `MODE`, `MODIFIED`, `READONLY` live in zero page.
  `FILE_LINE16` is the authoritative current line number; `CURSOR_ROW` is
  derived from it and `VIEW_TOP16`.
- **Read-only mode**: set if file load truncates; edit keys are ignored and
  `:w` / `:wq` are blocked.

## Memory layout

| Address | Size | Purpose |
|---------|------|---------|
| `$0000-$00FF` | 256 B | Zero page variables |
| `$0100-$01FF` | 256 B | 6502 stack |
| `$0200-$02FF` | 256 B | Filename buffer (`FNAME_BUF`) |
| `$0300-$03FF` | 256 B | Command buffer (`CMD_BUF`) |
| `$0400+` | Variable | Editor code (loads here) |
| `TEXT_BUF` | Variable | Text buffer (page-aligned after code, up to `$D5FF`) |
| `$D600-$D61F` | 32 B | Batch insert staging buffer (`BATCH_BUF`) |
| `$D620-$D653` | 52 B | Mark table (`MARK_TBL`), 26 marks x 2 bytes |
| `$D654-$D6FF` | 172 B | Search pattern buffer (`SEARCH_BUF`) |
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
| `j` / Down | Move down (with count) |
| `k` / Up | Move up (with count) |
| `0` / Home | Beginning of line |
| `$` / End | End of line |
| `^` | First non-blank character |
| `w` | Forward to next word start (with count) |
| `b` | Backward to previous word start (with count) |
| `e` | Forward to end of word (with count) |
| `G` | Go to last line; `[N]G` goes to line N |
| `gg` | Go to first line |
| Ctrl-F / PgDn | Page down (with count) |
| Ctrl-B / PgUp | Page up (with count) |
| Ctrl-Right | Word forward |
| Ctrl-Left | Word backward |
| `/` | Forward search |
| `?` | Backward search |
| `n` | Repeat search same direction (wraps) |
| `N` | Repeat search opposite direction |

### Normal mode — editing

| Key | Action |
|-----|--------|
| `i` | Insert at cursor |
| `a` | Insert after cursor |
| `A` | Insert at end of line |
| `o` | Open line below |
| `O` | Open line above |
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
| `r` | Replace character (with count) |
| `~` | Toggle case (with count, advances cursor) |
| `J` | Join lines (with count) |
| `>>` | Indent line by 2 spaces (with count for multi-line) |
| `<<` | Unindent line by up to 2 spaces (with count) |
| `yy` | Yank line (with count) |
| `yw` | Yank word forward (with count, character yank) |
| `yb` | Yank word backward (with count, character yank) |
| `p` | Paste below/after cursor (with count) |
| `P` | Paste above/before cursor (with count) |
| `u` | Undo last edit / redo (single-level toggle; covers deletes, changes, joins, opens, pastes, `r`, `~`, `>>`, `<<`, range shifts) |

### Normal mode — marks

| Key | Action |
|-----|--------|
| `ma`–`mz` | Set mark |
| `'a`–`'z` | Jump to mark |

### Normal mode — other

| Key | Action |
|-----|--------|
| `1`–`9` | Start count prefix; `0`–`9` continues (capped at 1000) |
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
| `:marks` | Display all set marks |
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
- Line paste (`p`/`P`): inserts whole lines below/above.
- Character paste: inserts inline after/before cursor.

## Rendering + input

- Uses ANSI escape sequences via `terminal.asm` helpers (cursor move, clear
  line, reverse video status bar).
- Long lines wrap across multiple screen rows (vi-style).
- Lines past EOF shown as `~` (tilde).
- Non-ASCII bytes shown as `?` in reverse video; control characters as spaces.
- Status bar shows: filename, `[RO]`, `[+]`, mode, count/pending, line,col,
  total lines.
- `input.asm` normalizes backspace and parses ESC sequences to high-bit key
  codes (`KEY_UP=$80`, `KEY_DOWN=$81`, etc.).
- Snapshot-based render optimization minimizes redraw work per keystroke.

## Performance

- **Batching**: the editor aggressively batches buffered input:
  - Printable chars in insert mode: up to 32 chars (mixed Enter/BS/printable)
    in one batch.
  - Backspace/Delete in insert mode: count and delete multiple at once.
  - Enter in insert mode: batch multiple newline insertions.
  - Join-lines (BS at column 0): batch multiple joins.
  - Movement keys: batch identical keys (e.g., multiple j/k/h/l).
  - Two-key combos (dd, yy, >>, <<, etc.): count additional pairs.
- **Page-optimized memory ops**: byte shifting uses inner Y-indexed loops
  processing 256 bytes per page.
- **Incremental line table updates**: single-char edits without newlines use
  `buf_adjust_lines_inc/dec` instead of full rebuild.
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
  via the emulator) and runs it under `./emulator.out`, feeding keystroke byte
  streams and verifying saved file contents and screen state.
- `editor/tests/ansi_screen.py` is a virtual terminal that processes ANSI
  escape sequences into a screen buffer for screen-state assertions.
- Bounds checking tests build `editor_small.out` with `define:small_buffer` to
  force truncation/read-only scenarios.
- On success, creates `editor/out/editor_stable.out` for use by `editor.sh`.

### Quick commands
```bash
# Run tests (from toolchain/asm2):
python3 editor/tests/editor_tests.py -q

# Run editor (console):
./editor.sh <file>
```

## Build/run

```bash
# Assemble (release):
./emulator.out 17/out/asm.out editor/editor.asm editor/out/editor.out

# Assemble (small buffer):
./emulator.out 17/out/asm.out editor/editor.asm editor/out/editor_small.out define:small_buffer

# Assemble (terminal mode):
./emulator.out 17/out/asm.out editor/editor.asm editor/out/editor_terminal.out define:terminal_mode

# Run (console):
./emulator.out editor/out/editor.out --load 0400 --console <file>

# Shortcut (uses editor_stable.out):
./editor.sh <file>
```

## Tips for LLMs making changes

- Any edit that changes buffer contents must update the line table (full
  `buf_rebuild_lines` if newlines changed, or `buf_adjust_lines_inc/dec` for
  single-char edits) and set `MODIFIED`.
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
