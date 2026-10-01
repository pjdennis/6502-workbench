# Editor UTF-8/Unicode Support Plan

> **Attic note:** historical. Paths (`22/`, `23/`, `editor/`, `assembler2/`) are from the old assembler2 layout; the live code is `asm/` (stages 00-17) and `editor/`. See `attic/assembler2/README.md`.


## Problem

The editor assumes **1 byte = 1 display column** throughout. When a file contains multi-byte UTF-8 characters, this causes:
- Cursor position displayed incorrectly (shifted right by extra bytes)
- Insertions appear at wrong visual position
- Line length calculations are wrong (bytes vs display columns)
- Backspace/delete can corrupt multi-byte sequences

## Root Cause

UTF-8 encodes characters as 1-4 bytes:
- `0xxxxxxx` ($00-$7F): 1 byte (ASCII)
- `110xxxxx` ($C0-$DF): 2 bytes
- `1110xxxx` ($E0-$EF): 3 bytes
- `11110xxx` ($F0-$F7): 4 bytes

Continuation bytes have the pattern `10xxxxxx` ($80-$BF).

When a 4-byte UTF-8 character appears before the cursor, `CURSOR_COL16` is 3 higher than the actual display column, causing the ANSI cursor to overshoot.

## Affected Functions

### Line length
- **`buf_get_line_len`** (`buffer.asm:176-191`) - Counts bytes until `\n`. Needs to count display columns (skip continuation bytes).

### Cursor-to-buffer mapping
- **`get_cursor_buf_ptr`** (`normal.asm:880-885`) - Adds `CURSOR_COL16` directly to line pointer. Needs to walk bytes, advancing column count only for non-continuation bytes.

### Rendering
- **`render_line_chars`** (`render.asm:324-346`) - Increments `RENDER_COL` per byte. Should only increment for lead bytes (non-continuation bytes).
- **`render_position_cursor`** (`render.asm:240-252`) - Uses `CURSOR_COL16 % SCREEN_COLS` for ANSI column. Affected transitively once CURSOR_COL16 tracks display columns.
- **`render_current_line_and_status`** (`render.asm:280-300`) - Length check for wrap detection.

### Cursor clamping
- **`clamp_cursor_col`** / **`clamp_cursor_col_insert`** - Uses line_len, affected transitively.

### Cursor movement
- **h/l movement** - Needs to skip over continuation bytes as a unit (move by character, not by byte).

### Editing operations
- **`insert_backspace`** (`insert.asm:164-333`) - Needs to delete whole multi-byte sequence, not just one byte.
- **`insert_delete`** (`insert.asm:336-422`) - Same.
- **`insert_char`** (`insert.asm:63-109`) - Insertion point calculation via `get_cursor_buf_ptr`.

### Line wrapping
- **`ensure_cursor_visible`** (`render.asm:407-553`) - Wrapping calculations use line length.
- **`line_screen_rows`** (`render.asm:383-401`) - Same.

## Approach

The key distinction: **display columns** (what the terminal shows) vs **byte offsets** (position in buffer). `CURSOR_COL16` should track display columns. Buffer operations need a conversion function from display column to byte offset.

### Core utility needed
A function like `col_to_byte_offset`: given a line pointer and a display column count, walk the bytes skipping continuation bytes to find the actual byte offset. This replaces the simple `CURSOR_COL16 + BUF_PTR16` addition in `get_cursor_buf_ptr`.

UTF-8 continuation byte test: `AND #$C0; CMP #$80` - if equal, it's a continuation byte (skip it for column counting).

### Scope decision
- **Basic UTF-8**: Treat each non-continuation byte as 1 display column. Handles accented characters, common symbols correctly.
- **Full unicode width**: Also handle wide characters (CJK, some emoji = 2 columns) and combining characters (0 columns). Much more complex, would need a width lookup table.

Basic UTF-8 support is the practical starting point.
