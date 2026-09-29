# Plan: Skip cursor row repaint on line paste undo

## Context

When undoing a line paste (`p`/`P`), `RENDER_FLAG = $02` triggers `render_line_delete_scroll` which always repaints the cursor row (lines 726-741 of render.asm). This repaint is needed for operations where cursor line content changes (J join, cc change), but for paste undo the cursor row is unmodified — only pasted lines below/above were deleted.

This mirrors the existing `$04` optimization: `$03` = line insert + repaint row above cursor, `$04` = line insert + skip row above cursor (used by J undo). We add the equivalent for line delete.

## RENDER_FLAG values (updated)

| Value | Meaning | Cursor row repaint |
|-------|---------|-------------------|
| $00 | Auto-detect | N/A |
| $01 | Current line only | Yes (that's the point) |
| $02 | Line delete scroll | Yes |
| $03 | Line insert scroll | Yes (row above cursor) |
| $04 | Line insert scroll, skip cursor | No |
| $05 | Line delete scroll, skip cursor | No (NEW) |

## Changes

### `editor/render.asm`

1. **Dispatch** (~line 459): Add `$05` routing to `.line_delete_scroll`:
```asm
  CMP #$02
  BEQ .line_delete_scroll
  CMP #$05
  BEQ .line_delete_scroll
  CMP #$03
```

2. **`render_line_delete_scroll`** (~line 726): Skip cursor row repaint block when `$05`:
```asm
  LDA RENDER_FLAG
  CMP #$05
  BEQ .cursor_no_clear
  ; existing cursor row repaint code...
```

3. **Comment** (line 28): Update RENDER_FLAG documentation.

### `editor/undo.asm`

**`undo_paste_undo`** (line 413): Change `$02` → `$05`.

## Verification

```bash
python3 editor/tests/editor_tests.py -q
```
