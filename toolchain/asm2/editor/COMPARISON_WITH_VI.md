# Vi vs. Our 6502 Editor: Architecture & Algorithm Comparison

## Overview

| Aspect | Original Vi (Bill Joy, ~1976) | Our Editor |
|--------|-------------------------------|------------|
| Language | C (~15,000 lines across 38 files) | 6502 Assembly (~7,500 lines across 15 files) |
| Platform | VAX/PDP Unix, termcap terminals | 6502 emulator, ANSI terminal |
| Memory | Virtual memory + disk temp file | 64KB flat memory, all in-core |
| Max file | Limited by disk, not RAM | ~40KB text buffer, 1023 lines |

---

## 1. Text Storage — The Biggest Architectural Difference

**Vi**: Uses a **temp-file-backed line array**. Lines are *not* stored in memory — they live in a disk-based temporary file accessed through block-level LRU caching (two 1KB/4KB input buffers + one output buffer). An in-core array of `line` pointers indexes into the temp file. This means vi can edit files far larger than available RAM.

**Our editor**: Uses a **contiguous in-memory byte buffer** with newline delimiters, plus a separate **line pointer table** (`LINE_TBL` at `$D800`, 2 bytes per entry, up to 1023 lines). Text lives entirely in RAM between `TEXT_BUF` and `BUF_END16`.

**Implications**:
- Vi pays disk I/O cost for every line access (`getline()` reads from temp file), mitigated by LRU buffering. Our editor has zero I/O cost — all data is directly addressable.
- Vi's insertions/deletions only manipulate the pointer array and write new blocks to the temp file. Our editor must **shift the entire tail of the buffer** for every insert/delete — an O(n) operation on file size.
- Our editor mitigates this with **page-at-a-time memory copy** (16-18 cycles/byte vs. 47 naive) and **batch consolidation** in insert mode.

**Planned convergence**: Our `PERFORMANCE.md` outlines a gap buffer as step 5, which would make insert/delete O(1) at the cursor — a different solution than vi's temp file but solving the same problem.

---

## 2. Line Table Maintenance

**Vi**: The line pointer array is the *primary* data structure. Inserting/deleting lines means splicing the array (moving pointers, not text). New line content is appended to the temp file. Cost: O(lines_moved) pointer shuffling, but the text itself isn't touched.

**Our editor**: The line table is a *derived* index rebuilt from the text buffer. Three strategies:
- **Full rebuild** (`buf_rebuild_lines`): scan entire buffer for newlines — O(file_size). Used when newlines are added/removed.
- **Incremental adjust** (`buf_adjust_lines_apply`): walk entries after edit point, adjust by the signed size change — O(remaining_lines). Used for edits within one line (no newline changes).

This is fundamentally different: vi's pointers *are* the canonical representation; our pointers are a cache over the byte buffer.

---

## 3. Display/Rendering

**Vi**: Extremely sophisticated terminal abstraction via **termcap**. Supports four display modes (full visual, CRT open, dumb terminal, hardcopy). Uses `vlinfo[]` to track per-line screen depth and dirty flags. Optimizes with character-level insert/delete, line-level scroll operations, and smart cursor movement. The `Outchar`/`Putchar`/`Pline` function pointers allow swapping rendering strategies.

**Our editor**: Uses **snapshot-based render optimization**. Before each command, captures `SNAP_VIEW_TOP16`, `SNAP_LINE_COUNT16`, `SNAP_BUF_END16`. After the command, `render_decide` compares:
- View top changed -> full redraw
- Buffer end changed -> redraw current line + status
- Nothing changed -> reposition cursor only

This is simpler but effective. No per-line dirty tracking, no character-level insert/delete optimization. Always uses ANSI escape sequences (no termcap abstraction needed).

**Trade-off**: Vi's approach minimizes bytes sent to slow serial terminals (critical in the 1970s). Our approach is simpler to implement and correct, relying on modern terminal emulators being fast enough that full-line redraws are cheap.

---

## 4. Undo

**Vi**: Multi-level undo with five undo types (`UNDCHANGE`, `UNDMOVE`, `UNDALL`, `UNDNONE`, `UNDPUT`). Saves original lines between `dol` and `unddol` in the temp file. Visual mode adds single-line undo (`vutmp` buffer) and the `U` command (full line restore). The `FIXUNDO` macro controls recording granularity.

**Our editor**: Single-level undo/redo: `u` undoes the most recent operation and toggles to redo on repeat. Covers delete/change/substitute/join/open/paste plus `r`, `~`, `>>`, `<<`, and range shift commands. Deleted content is restored from the yank buffer, so a later yank ends undo of a delete or paste (vi's undo is independent of yanks); small per-operation state (replaced chars, per-line indent widths, join offsets) lives in a shared 256-byte undo data page.

---

## 5. Search

**Vi**: Full **regular expression engine** based on `ed` — supports `.`, `*`, `^`, `$`, `[]`, `\(\)` groups, backreferences, and `&` in substitutions. Compiled to an internal representation (`Expbuf[]`). Integrated with `:s///` substitution and `:g//` global commands.

**Our editor**: **Literal string search** only. Forward (`/`) and backward (`?`) with wrap-around. Brute-force matching: for each position in each line, compare pattern bytes sequentially. Pattern reuse (empty search repeats last). ~172-byte pattern buffer.

**Algorithm comparison**: Both use the same basic structure (iterate lines, check each position), but vi compiles patterns for repeated use while ours does direct byte comparison. Vi's regex adds significant complexity (~17KB in `ex_re.c` alone).

---

## 6. Command Dispatch

**Vi**: Uses a giant `switch` statement in `vmain()` with ~40+ cases. Count prefix handling, register selection (`"a`), and operator-motion composition (`d`, `c`, `y` combined with any motion) are woven into the main loop. The operator/motion model is the heart of vi's composability.

**Our editor**: Uses **dispatch tables** — arrays of `[key, handler_lo, handler_hi]` entries scanned linearly. Two-key combos use a **pending dispatch table** with `[key1, key2, flags, handler_lo, handler_hi]`. Flags control batch pairing and read-only blocking.

**Key difference**: Vi's operator-motion composability (`d3w`, `c$`, `y{`) comes from its operator/operand architecture in `ex_voper.c`. Our editor handles specific combos explicitly (`dd`, `dw`, `cw`, etc.) rather than composing operators with arbitrary motions. This is less general but simpler to implement in assembly.

---

## 7. Insert Mode

**Vi**: Character-at-a-time insertion. Each keystroke immediately modifies `linebuf` and updates the display. `putline()` writes the completed line to the temp file on exit.

**Our editor**: **Unified batch handler** — collects up to 32 mixed keystrokes (printable, Enter, Backspace, Delete), consolidates on-the-fly into canonical form `[back N][insert chars][fwd N]`, then performs a single buffer shift and copy. This is a significant optimization: N keystrokes cost 1 shift instead of N shifts.

This is arguably more sophisticated than vi's approach for the specific constraint of expensive buffer shifts on a 6502.

---

## 8. Memory Management

**Vi**: Dynamic allocation via `sbrk()`. Line pointer array grows upward, undo area sits above `dol`, guard checks against `endcore`. The temp file provides virtually unlimited text storage.

**Our editor**: **Static memory map** with fixed regions. Text buffer floats after code (`TEXT_BUF = _code_end` page-aligned). Line table fixed at `$D800`. Yank buffer at `$E000`. Everything has hard limits but zero allocation overhead.

---

## 9. Marks

**Vi**: 26 named marks stored as `line` pointers (references into temp file). `'a` jumps to the marked line.

**Our editor**: 26 marks stored as 16-bit line numbers at `MARK_TBL` ($D620). **Auto-adjustment** on bulk operations: marks shift when lines are inserted/deleted, and marks within deleted ranges are cleared. Vi doesn't auto-adjust marks — they become stale if the referenced line is deleted.

Our mark adjustment is actually more robust than vi's.

---

## 10. Feature Comparison Summary

| Feature | Vi | Our Editor |
|---------|-----|------------|
| File size limit | Disk-bounded | ~40KB RAM |
| Undo | Multi-level | Single-level undo/redo toggle |
| Regex search | Full (ed-style) | Literal only |
| Operator-motion | Composable (`d3w`) | Explicit combos (`dd`, `dw`) |
| Named registers | 26 + numbered | 1 yank buffer |
| Macros (`@a`) | Yes | No |
| `:s///` substitute | Yes (with regex) | No |
| `:g//` global | Yes | No |
| Range commands | Full (`:1,10d`) | Yes (`:1,10d`, `:1,10y`, `:1,10>`) |
| Marks | 26, no auto-adjust | 26, auto-adjusted |
| Insert batching | No (char-at-a-time) | Yes (up to 32 keys) |
| Terminal abstraction | Termcap (4 modes) | ANSI only |
| Line wrapping | Yes | Yes |
| Word motion | w/b/e/W/B/E | w/b/e |
| Indent/unindent | `>>`, `<<` | `>>`, `<<`, range |

---

## Architectural Verdict

The two editors solve fundamentally different problems within their constraints:

**Vi** was designed for large files on systems with more RAM than a 6502 but slow terminals. Its temp-file architecture trades disk I/O for unlimited file size, and its display engine minimizes terminal output. The operator-motion grammar makes it endlessly composable.

**Our editor** was designed for a 64KB address space with no disk. Its contiguous buffer + batch optimization trades file size limits for zero I/O overhead and minimal code complexity. The snapshot-based renderer and insert-mode batching are clever adaptations to the constraint that shifting bytes is expensive on a 6502 but screen output is comparatively cheap.

The most interesting algorithmic divergence is in insert mode: vi writes each character immediately (cheap with a temp file), while our editor batches aggressively (essential when every insert shifts the entire buffer tail). Our approach is arguably the more sophisticated algorithm for its constraint set.
