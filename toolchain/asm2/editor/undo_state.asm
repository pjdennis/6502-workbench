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
;   3 = cc/S (like line-delete, but one empty line replaced the lines)
;   4 = line-paste-below (p with line yank)
;   5 = line-paste-above (P with line yank)
;   6 = char-paste-below (p with char yank)
;   7 = char-paste-above (P with char yank)
;   8 = join (J, NJ)
;   9 = open-line (o/O opened blank line(s))
;  10 = indent (spaces were added; undo removes them via unindent)
;  11 = unindent (spaces were removed; undo re-inserts recorded counts)
;  12 = toggle case (~; self-inverse, undo/redo re-toggle the span)
;  13 = replace char (r; originals in UNDO_DATA_BUF, redo re-writes;
;       the replacement KEY_ENTER is r<Enter>'s line break)
;
; Types 1-7 read the yank buffer (the deleted text, the paste size), so
; a new yank ends them (yank_store); from UNDO_JOIN up, the types keep
; their own data and survive a yank.
;
; Types 10/11 are self-morphing: undoing an indent re-records as an
; unindent and vice versa, so repeated 'u' toggles without UNDO_IS_REDO.
;
; The record fields are shared.  What each type keeps in them (UNDO_
; prefix dropped, - = unused):
;   type          LINE16           COL16          JOIN_COUNT   PASTE_COUNT16
;   1 dd, :d      first line       u's column     empty line   -
;   2 x, d, c     cursor line      cursor column  -            -
;   3 cc          first line       u's column     empty line   -
;   4 p lines     line above copy  cursor column  -            copies
;   5 P lines     first line       cursor column  -            copies
;   6/7 p/P chars cursor line      insert column  -            copies
;   8 J           first line       join column    joins        typed column
;   9 o/O         opened line      line to return -            -
;   10/11 >> <<   first line       cursor column  -            lines
;   12 ~          cursor line      span start     span length  -
;   13 r          cursor line      span start     span length  replacement
; Per-type alias names are declared below the fields.  While ~ runs,
; PASTE_COUNT16 is the last visited column (TILDE_LAST_COL16).

UNDO_NONE = 0
UNDO_LINE = 1
UNDO_CHAR = 2
UNDO_CC   = 3
UNDO_LINE_PASTE_BELOW = 4
UNDO_LINE_PASTE_ABOVE = 5
UNDO_CHAR_PASTE_BELOW = 6
UNDO_CHAR_PASTE_ABOVE = 7
UNDO_JOIN = 8
UNDO_OPEN = 9
UNDO_INDENT = 10
UNDO_UNINDENT = 11
UNDO_TILDE = 12
UNDO_REPLACE = 13

; Shared per-operation undo data (single-level undo, so one page serves
; all users): join = 16-bit newline offsets from the line start,
; indent/unindent = per-line widths, replace = the original chars, char
; delete = the marks before it (mark_save).
UNDO_DATA_BUF = $D700     ; 256 bytes
JOIN_UNDO_MAX = 128       ; 256 / 2 bytes per entry

; (zero-page variables: zp.asm)
; Per-type names for the shared record fields (zero-cost aliases)
UNDO_EMPTY_LINE    = UNDO_JOIN_COUNT     ; dd cc: bit 7 = u first removes the
                                         ; empty line left at UNDO_LINE16
UNDO_SPAN_LEN      = UNDO_JOIN_COUNT     ; ~ r: chars in the span
UNDO_RANGE_LINES16 = UNDO_PASTE_COUNT16  ; >> <<: lines in the range (> 255: not undoable)
UNDO_REPL_CHAR     = UNDO_PASTE_COUNT16  ; r: the replacement char
UNDO_JOIN_COL16    = UNDO_PASTE_COUNT16  ; J: the column the (last) J was typed at
