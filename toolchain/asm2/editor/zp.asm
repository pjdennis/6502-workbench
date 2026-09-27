; Zero-page variables of every editor module, gathered here and
; included before any code so every zero-page reference is a backward
; one (asm17 assembles a forward reference as absolute: one more byte
; and one more cycle).  Grouped by owning module, in include order.

  .zeropage

; --- terminal.asm ---
ANSI_ROW:     .byte    ; Where the last cursor move put the cursor (1-based;
ANSI_COL:     .byte    ;   a scroll region's top and bottom while one is set)
CUR_VALID:    .byte    ; 1 from a frame's end until the cursor next moves: it
                       ;   is still at ANSI_ROW/ANSI_COL (ansi_goto0)
STR_PTR16:    .word    ; Pointer for write_string
DEC_VALUE16:  .word    ; The number write_param and print_decimal write
DEC_PAD:      .byte    ; The char a leading zero is written as (0 = none)
DEC_TEXT:     .byte    ; Bit 7: the digits go through text_putc, not io_write
TEXT_LEFT:    .byte    ; text_putc: 1 + characters still allowed on the status row

; --- input.asm ---
PUSHBACK:         .word  ; Pushback stack, top first (PUSHBACK_COUNT deep)
PUSHBACK_COUNT:   .byte  ; Bytes pushed back: 0, 1 or 2
KEY_DECODED:      .byte  ; Buffered decoded key
HAS_KEY_DECODED:  .byte  ; $FF if KEY_DECODED has a value, else $00

; --- buffer.asm ---
BUF_END16:     .word     ; Points one past last byte of text
LINE_COUNT16:  .word     ; Number of lines in buffer (16-bit)
BUF_PTR16:     .word     ; General-purpose buffer pointer
BUF_SRC16:     .word     ; Source pointer for block moves
BUF_DST16:     .word     ; Destination pointer for block moves
BUF_LEN16:     .word     ; Length/count for block moves
BUF_TEMP:      .byte     ; Shared scratch byte
BUF_TEMP16:    .word     ; 16-bit count for line operations (delete, yank, etc.)
BUF_DELTA:     .byte     ; Shared scratch byte (insert length, loop counts)
FILE_HANDLE:   .byte     ; File handle for load/save

; --- undo_state.asm ---
UNDO_TYPE:       .byte    ; UNDO_NONE..UNDO_INSERT (undo_state.asm)
UNDO_LINE16:     .word    ; Record fields: see the per-type table in undo_state.asm
UNDO_COL16:      .word
UNDO_IS_REDO:    .byte    ; 0=undo pending, $FF=redo pending
INSERT_SEG:      .byte    ; Insert mode's undo segment: 0 = none (the next change
                          ; starts one), $FF = its record is kept, other = its
                          ; changes clear the undo (insert_segment)
UNDO_JOIN_COUNT: .byte
UNDO_PASTE_COUNT16: .word
UNDO_RET_COL16:  .word    ; insert of o and O: the column u returns to

; --- render.asm ---
CURSOR_ROW:     .byte   ; Cursor screen row (0-based, derived from wrap computation)
FILE_LINE16:    .word   ; Current file line (0-based); CURSOR_COL16 follows it, as
                        ; SNAP_COL16 follows SNAP_LINE16 (insert mode's move test)
CURSOR_COL16:   .word   ; Cursor column (0-based, 16-bit for lines >255 chars)
VIEW_TOP16:     .word   ; First visible line number (0-based)
SCREEN_ROWS:    .byte   ; Terminal height
SCREEN_COLS:    .byte   ; Terminal width
TEXT_ROWS:      .byte   ; SCREEN_ROWS - 1: text rows above the status bar
MODE:           .byte   ; Current mode: MODE_NORMAL, MODE_INSERT
MODIFIED:       .byte   ; File modified flag ($00 = no, $FF = yes)
READONLY:       .byte   ; Read-only mode ($00 = no, nonzero = yes)
RENDER_ROW:     .byte   ; Current row being rendered
RENDER_LINE16:  .word   ; Current file line being rendered
RENDER_COL:     .byte   ; Column counter during rendering
RENDER_FLAG:    .byte   ; Handler's render request: RF_* (render.asm; contract table in render_decide.asm)
VIEW_TOP_WRAP:  .byte   ; Wrap row offset for first visible line (0 = start of line)
WRAP_QUOT:      .byte   ; Cursor's wrap row (CURSOR_COL16 / SCREEN_COLS), set by ensure_cursor_visible
WRAP_REM:       .byte   ; Scratch: column a partial / ICH-DCH row render starts at
RENDER_WRAP:    .byte   ; Current wrap row offset during rendering
DIV_INPUT16:    .word   ; Scratch for 16-bit division
PREV_LINE_ROWS: .byte   ; Screen rows the cursor line occupied before the key ($09: the split line's; $0B: the range's old rows)
SNAP_VIEW_TOP16: .word  ; Snapshot of VIEW_TOP16 before handler
SNAP_VIEW_TOP_WRAP: .byte ; Snapshot of VIEW_TOP_WRAP before handler
SNAP_LINE_COUNT16: .word ; Snapshot of LINE_COUNT16 before handler
SNAP_BUF_END16: .word   ; Snapshot of BUF_END16 before handler
SNAP_LINE16:    .word   ; The cursor before the key (a refused yank returns it there)
SNAP_COL16:     .word
SCROLL_DELTA:   .byte   ; Screen rows to scroll; rows to draw for render_limited_from_col (not reset per key)
RENDER_LIMIT:   .byte   ; render_rows: stop row (exclusive; $FF = the status bar); also a scratch counter
DELETE_SCREEN_ROWS: .byte ; Pre-computed rows for $06/$07/$08/$0B (0 = none; reset per key)
RENDER_FROM_COL16: .word  ; First affected line column for partial render ($FFFF = full line)
INSERT_LINE_COUNT:  .byte ; Per-flag line count / join or Enter kind (see RENDER_FLAG; reset per key)
CUR_LINE_ROWS:  .byte   ; Screen rows the cursor line (or $0B range) occupies after the edit
SHIFT_NET:      .byte   ; ICH/DCH hint: cells inserted (+) / deleted (-) at RENDER_FROM_COL16
SHIFT_WRITE:    .byte   ; ICH/DCH hint: new cells written from RENDER_FROM_COL16; $FF = no hint
RENDER_STOP:    .byte   ; render_line_chars_to: stop column (exclusive)
ROW_END:        .byte   ; shift: end of the line's content on the row (exclusive)
ROW_WEND:       .byte   ; shift: end of the cells to write on the row (exclusive)
SHIFT_DCH_COST: .byte   ; shift: byte cost of the DCH route for the row
SHIFT_REM16:    .word   ; shift: line length from the current row's start
SHIFT_IEND16:   .word   ; shift: end of the new cells from the current row's start (signed)
ST_COL:         .byte   ; status bar: length of the text built (status_build)
ST_LEN:         .byte   ; status bar: length of the text on the row (0 = unknown: clear it)
ST_FIRST:       .byte   ; status bar: first column to send ($FF = unchanged)
STATUS_HOLD:    .byte   ; 1: a message stays on the status row for the next frame
ST_BUILD:       .byte   ; $FF while status_build runs (text_putc stores the text)

; --- yank.asm ---
YANK_END16:    .word     ; Points one past last byte in yank buffer
YANK_LINES16:  .word     ; Lines a paste adds per copy (the yank's newlines)
YANK_SIZE16:   .word     ; Single yank size for paste operations
YANK_TYPE:     .byte     ; 0=line, 1=char

; --- search.asm ---
SEARCH_LEN:   .byte     ; Length of current search pattern
SEARCH_FIRST: .byte     ; Its first char (search_match_from's quick test)
SEARCH_LINE16: .word    ; Line number being searched
SEARCH_DIR:   .byte     ; Search direction: 0=forward (/), $10=backward (?)
SEARCH_LIMIT16: .word   ; search_line_walk stops at the first match at or after this address

; --- normal_util.asm ---
LAST_KEY:       .byte  ; Previous key for multi-key commands (dd, gg, yy, m, ')
LINE_LEN16:     .word  ; Cached length of current line (16-bit)
DISPATCH_PTR16: .word  ; Pointer into dispatch table during scan
JUMP_TARGET16:  .word  ; Target for indirect jump
COUNT16:        .word  ; Accumulated count (0 = no count entered)
NORMAL_TEMP:    .byte  ; Temp byte for normal mode operations
SCROLL_AMOUNT:  .byte  ; Sticky scroll amount for Ctrl-D/U (0 = half-page default)
BATCH_RESTORE_KEY: .byte ; Key to restore to LAST_KEY after batch (0 = none)
BATCH_EXTRA:       .byte ; Number of extra pairs found by batch_pending_pairs (0 = none);
                         ; main_loop zeroes it for every key
CURSWANT16:        .word ; The column j/k/Up/Down aim at (vim's curswant; $FFFF: line ends)
CURSWANT_KEEP:     .byte ; Nonzero: the last key was a vertical move, so CURSWANT16
                         ; holds (it sets 2, main_loop halves it for every key)

; --- word.asm ---
WORD_CLASS:    .byte     ; Character class of current char
WORD_OP:       .byte     ; 1 while an operator runs word_forward_x, else 0
OP_EXCL_LINE:  .byte     ; Bit 7: a w or b operator's range ended on column 0
                         ; of a later line (op_lines reads and clears it)

; --- normal_shift.asm ---
SHIFT_MODE: .byte       ; insert_spaces_core width source (0=const, $FF=data);
                        ; also TILDE_TOGGLED (normal_edit.asm)
SHIFT_PREV_WIDTH: .byte ; the part of BUF_DELTA a batch's earlier >> / <<
                        ; pairs take (0 unless batched)

; --- command.asm ---
FNAME_PTR16: .word     ; The file name: the argument, or "[No Name]"
CMD_IDX:     .byte     ; Current index into command buffer
CMD_QUIT:    .byte     ; Set to $FF when editor should quit

; --- mark.asm ---
MARK_DELTA16: .word

  .code
