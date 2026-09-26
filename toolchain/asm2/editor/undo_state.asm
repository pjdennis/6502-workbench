; Undo/redo state for the normal-mode editing commands
;
; Single-level undo: 'u' toggles between undo and redo.  Deletes and
; pastes keep their text in the yank buffer, so undo = paste it back (or
; delete the pasted text) and redo = repeat the operation; the other
; types record what they need in the fields below.
;
; UNDO_TYPE values:
;   0 = none (no undoable operation)
;   1 = line-delete (dd, 2dd, etc.)
;   2 = char-delete (x, X, D, d$, d0, dw, db, de; s, C, cw, cb, ce)
;   3 = cc/S line-delete (like line-delete but cc inserted blank line)
;   4 = join (J, NJ)
;   5 = line-paste-below (p with line yank)
;   6 = line-paste-above (P with line yank)
;   7 = char-paste-below (p with char yank)
;   8 = char-paste-above (P with char yank)
;   9 = open-line (o/O opened blank line(s))
;  10 = indent (spaces were added; undo removes them via unindent)
;  11 = unindent (spaces were removed; undo re-inserts recorded counts)
;  12 = toggle case (~; self-inverse, undo/redo re-toggle the span)
;  13 = replace char (r; originals in UNDO_DATA_BUF, redo re-writes)
;
; Types 10/11 are self-morphing: undoing an indent re-records as an
; unindent and vice versa, so repeated 'u' toggles without UNDO_IS_REDO.
;
; The record fields are shared.  What each type keeps in them (UNDO_
; prefix dropped, - = unused):
;   type          LINE16           COL16          JOIN_COUNT   PASTE_COUNT16
;   1 dd, 3 cc    first line       -              -            -
;   2 x, d, c     cursor line      cursor column  -            -
;   4 J           first line       join column    joins        -
;   5 p lines     line above copy  cursor column  -            copies
;   6 P lines     first line       cursor column  -            copies
;   7/8 p/P chars cursor line      insert column  -            copies
;   9 o/O         opened line      line to return -            -
;   10/11 >> <<   first line       cursor column  width        lines
;   12 ~          cursor line      span start     span length  -
;   13 r          cursor line      span start     span length  replacement
; While J runs, COL16 is its batching flag; while ~ runs, PASTE_COUNT16
; is the last visited column.

UNDO_NONE = 0
UNDO_LINE = 1
UNDO_CHAR = 2
UNDO_CC   = 3
UNDO_JOIN = 4
UNDO_LINE_PASTE_BELOW = 5
UNDO_LINE_PASTE_ABOVE = 6
UNDO_CHAR_PASTE_BELOW = 7
UNDO_CHAR_PASTE_ABOVE = 8
UNDO_OPEN = 9
UNDO_INDENT = 10
UNDO_UNINDENT = 11
UNDO_TILDE = 12
UNDO_REPLACE = 13

; Shared per-operation undo data (single-level undo, so one page serves
; all users): join = 16-bit newline offsets from the line start,
; indent/unindent = per-line widths, replace = the original chars.
UNDO_DATA_BUF = $D700     ; 256 bytes
JOIN_UNDO_MAX = 128       ; 256 / 2 bytes per entry

  .zeropage

UNDO_TYPE:       .byte    ; UNDO_NONE..UNDO_REPLACE (see above)
UNDO_LINE16:     .word    ; Record fields: see the per-type table above
UNDO_COL16:      .word
UNDO_IS_REDO:    .byte    ; 0=undo pending, $FF=redo pending
INSERT_CHANGED:  .byte    ; Insert mode: nonzero once the buffer changed
                          ; (leaving insert mode then clears the undo record)
UNDO_JOIN_COUNT: .byte
UNDO_PASTE_COUNT16: .word

  .code
