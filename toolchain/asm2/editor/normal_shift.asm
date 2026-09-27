; Normal-mode shift and span operations: >> / << (with the shared
; insert/remove space cores used by range commands and undo), plus
; line-content helpers, the dollar and zero commands (D, d$, y$, d0, y0;
; C in normal_edit.asm shares the $ range setup) and the word operators
; (dw/db/de, cw/cb/ce; yw/yb/ye in normal_move.asm enter here).  Split
; from normal_edit.asm; see that file for paste/join/substitute/replace.


; --- Indent (>>) and unindent (<<) ---
;
; Both are built on two shared cores that operate on an arbitrary line
; range: insert_spaces_core (add leading spaces) and remove_spaces_core
; (strip leading spaces).  The cores are also used by the :[range]> and
; :[range]< commands and by undo/redo of these operations.
;
; Core input contract:
;   FILE_LINE16  = first line of the range (the cursor is on it)
;   CURSOR_COL16 = the column u returns to (vim's operator start)
;   BUF_TEMP16   = number of lines in the range (0 = do nothing)
;   BUF_DELTA    = space width W (insert per non-empty line / max removal)
;   SHIFT_PREV_WIDTH = the part of W that a batch's earlier pairs take
;                  (0 unless batched)
;   SHIFT_MODE   = insert core only: 0 = constant width W per non-empty
;                  line; $FF = per-line widths from UNDO_DATA_BUF (undo)
; On return LINE_LEN16 = the line after the range (unless the buffer was
; full: shift_full).
;
; On change the cores set MODIFIED and render flags (RF_RANGE partial
; repaint when possible, else RF_FULL), and record undo for ranges up to
; 255 lines: UNDO_LINE16, UNDO_COL16 (the cursor column, moved as a
; batch's earlier pairs moved the first non-blank), UNDO_RANGE_LINES16
; and the per-line widths in UNDO_DATA_BUF (indexed by SHIFT_LINE_IDX
; while they run).  Undo covers the last >> / <<, one INDENT_WIDTH step:
; batched pairs multiply W, but u behaves as if the keys ran separately.
; On no-op (nothing inserted/removed) they leave MODIFIED and RENDER_FLAG
; untouched so the frame is a pure cursor/status update, and record an
; empty change, as vim does: u then puts the cursor back where the shift
; started (its widths are all 0, so the undo and the redo change nothing).  A shift refused at buffer full
; leaves the undo record as it was: until the shift has happened the
; cores keep their state out of it.

; (zero-page variables: zp.asm)

; Scratch the cores reuse while they run (aliases)
SHIFT_LINE_IDX   = BUF_TEMP        ; line index into UNDO_DATA_BUF
SHIFT_LINES16    = MARK_DELTA16    ; lines in the range (BUF_TEMP16 counts them off)

INDENT_WIDTH = 2

; >> and <<: the cursor ends on the first non-blank, as in vim
do_indent:
  JSR get_count_clamp_lines    ; BUF_TEMP16 = line count
  JSR shift_normal_setup
  JSR insert_spaces_core
  JMP first_nonblank_clear

do_unindent:
  JSR get_count_clamp_lines
  JSR shift_normal_setup
  JSR remove_spaces_core
  JMP first_nonblank_clear

; Shared >> / << entry setup, after get_count_clamp_lines (which ends
; the command for a count on the last line).  Computes BUF_DELTA =
; INDENT_WIDTH * (1 + BATCH_EXTRA).  A count means lines and a repeated
; pair width, so the typed-ahead pairs merge (multiplying the width)
; only when no count was typed: 3>>>> is 3>> then >>.  The cursor goes where vim starts the
; operator, the column u returns to: over two or more lines the cursor,
; on one line the first non-blank if it is further left.  A batch's
; later pairs each start on the first non-blank the pair before left
; (the cores move it as the earlier pairs moved the text).  Near a full
; buffer (no room for a full batch) the pairs run one at a time, so the
; ones that fit go in and the next is refused on its own, as typed singly.
shift_normal_setup:
  LDX #0                       ; No pairs taken
  LDA COUNT16
  ORA COUNT16 + 1
  BNE .single
  LDA BUF_END16
  CMP #<TEXT_LIMIT - BATCH_MAX - BATCH_MAX - INDENT_WIDTH
  LDA BUF_END16 + 1
  SBC #>TEXT_LIMIT - BATCH_MAX - BATCH_MAX - INDENT_WIDTH
  BCS .single                  ; Under INDENT_WIDTH * (BATCH_MAX + 1) free
  JSR batch_pending_pairs      ; X = BATCH_EXTRA
.single:
  TXA
  ASL                          ; *INDENT_WIDTH (hardcoded: ASL assumes INDENT_WIDTH = 2)
  STA SHIFT_PREV_WIDTH         ; The earlier pairs' width (C = 0: BATCH_EXTRA <= BATCH_MAX)
  ADC #INDENT_WIDTH            ; + the last pair's
  STA BUF_DELTA                ; BUF_DELTA = INDENT_WIDTH * (1 + extra pairs)
  LDA BUF_TEMP16 + 1
  BNE .start                   ; (256 lines or more)
  LDX BUF_TEMP16
  DEX
  BNE .start                   ; Two or more lines: the cursor column
  LDA BATCH_EXTRA
  BEQ .one_line
  STA CURSOR_COL16 + 1         ; Batched: the first non-blank
.one_line:
  JSR nonblank_left
.start:
  LDA #0
  ; fall through

; Shared tail: SHIFT_MODE = A
shift_mode_a:
  STA SHIFT_MODE
  RTS

; One INDENT_WIDTH step in constant-width mode (the :range > / < setup,
; and undo)
shift_unit_setup:
  LDA #INDENT_WIDTH
  STA BUF_DELTA
  LDA #0
  STA SHIFT_PREV_WIDTH
  BEQ shift_mode_a             ; Always taken

; Common core prologue: save the range size, zero the per-core
; accumulators, pre-compute the range's current screen rows for the
; RF_RANGE render path, and set the line iterator (LINE_LEN16) to the
; range start.  The core loops test at the bottom, so an empty range
; (BUF_TEMP16 = 0: >> / << after a defect has left the cursor past the
; last line) returns from the core itself, a no-op as before.
shift_prologue:
  CP16 BUF_TEMP16, SHIFT_LINES16
  JSR shift_rewind             ; (A = 0)
  STA DELETE_SCREEN_ROWS       ; 0 = no partial repaint (fall back to full)
  LDA BUF_TEMP16 + 1
  BNE .done                    ; > 255 lines: full repaint, no undo
  LDA BUF_TEMP16
  BEQ .empty
  JMP compute_delete_rows_at_cursor
.empty:
  PLA                          ; Drop the return into the core: return
  PLA                          ; to the core's caller
.done:
  RTS

; Start the core's line loop at the range's first line: the line
; iterator LINE_LEN16 = FILE_LINE16, the lines left BUF_TEMP16 =
; SHIFT_LINES16, the line index for UNDO_DATA_BUF and the total shift or
; removal COUNT16 = 0.  Returns A = 0
shift_rewind:
  CP16 SHIFT_LINES16, BUF_TEMP16
  CP16 FILE_LINE16, LINE_LEN16
  LDA #0
  STA COUNT16
  STA COUNT16 + 1
  STA SHIFT_LINE_IDX
  RTS

; BUF_PTR16 = the start of line LINE_LEN16 before the core moved it,
; from its line table entry, which then gets the line's new start: the
; write pointer (JUMP_TARGET16), where the core is about to put it (the
; line's own start while the core has moved nothing, COUNT16 = 0).  The
; line count never changes, so the cores keep the table current line by
; line, and move the lines after the range at the end (shift_finish).
; Clobbers A, X, Y
shift_line_start:
  LDAX16 LINE_LEN16
  JSR buf_line_entry           ; BUF_PTR16 = the entry
  LDA COUNT16
  ORA COUNT16 + 1
  TAX                          ; X = 0: nothing moved yet
  LDY #1
.swap:
  LDA (BUF_PTR16),Y
  PHA                          ; The old start (high byte first)
  CPX #0
  BNE .moved
  STA JUMP_TARGET16,Y          ; The write pointer is at the line
.moved:
  LDA JUMP_TARGET16,Y
  STA (BUF_PTR16),Y
  DEY
  BPL .swap
  PLA
  STA BUF_PTR16
  PLA
  STA BUF_PTR16 + 1
  RTS

; Record undo of type A, move the lines after the range with it, then
; the render epilogue
shift_finish:
  JSR shift_record
  ; The line after the range (LINE_LEN16) now starts at the write pointer
  ; (JUMP_TARGET16): it and the lines after it move by the difference
  LDAX16 LINE_LEN16
  JSR buf_get_line_ptr         ; BUF_PTR16 = where it started
  SEC
  SBC16 JUMP_TARGET16, BUF_PTR16, BUF_SRC16
  LDA LINE_LEN16
  JSR buf_adjust_lines_from    ; (X kept by buf_get_line_ptr)

; Common core epilogue for a successful change: set MODIFIED and pick the
; render level.  Partial repaint (RF_RANGE) requires pre-computed screen
; rows (render derives the range's screen position from the cursor, which
; is on its first line).
shift_set_render:
  JSR set_modified
  LDA DELETE_SCREEN_ROWS
  BEQ .full
  LDA SHIFT_LINES16
  STA INSERT_LINE_COUNT        ; range line count for render
  LDA #RF_RANGE
  STA RENDER_FLAG              ; range repaint
  RTS
.full:
  LDA #RF_FULL
  STA RENDER_FLAG
  RTS

; Record undo of type A unless the range was too big for undo data (then
; there is nothing to undo)
shift_record:
  LDX SHIFT_LINES16 + 1
  BEQ .record
  LDA #UNDO_NONE               ; Big range: not undoable
.record:
  JSR undo_rec_set             ; Type, cursor position
  CP16 SHIFT_LINES16, UNDO_RANGE_LINES16
  RTS

; Buffer full: say so, and end the command there (the core's caller
; would report or move the cursor), with the cursor where the operator
; started, as vim leaves it after an operator that fails
shift_full:
  JSR show_buffer_full_msg
  PLA                          ; Drop the return into the core's caller
  PLA
  JMP clamp_and_clear_count    ; (undo put the cursor on the line it restores)

; Insert leading spaces into each line of a range (see contract above).
; Constant mode skips empty lines; data mode uses UNDO_DATA_BUF widths.
insert_spaces_core:
  JSR shift_prologue

  ; --- Pre-scan: total shift and the cursor line's width ---
.prescan:
  LDAX16 LINE_LEN16
  JSR buf_get_line_ptr
  JSR shift_line_width         ; A = width for this line
  TAY
  JSR shift_count_line
  BNE .prescan

  ; Nothing to insert (all lines empty): an empty change
  TST16 COUNT16
  BEQ .noop

  ; Single buffer shift right at first line start
  CP16 COUNT16, BUF_LEN16
  JSR get_current_line_ptr
  JSR buf_shift_right_16
  BCS shift_full               ; Buffer full: nothing changed

  ; --- Redistribute: write per-line spaces, copy line content down ---
  JSR shift_rewind             ; The range's lines again, and the total

.redist:
  JSR shift_line_start         ; The line's start before the shift, ...
  CLC
  ADC16 BUF_PTR16, BUF_LEN16, BUF_PTR16 ; ... which moved it by the total
  JSR shift_line_width         ; read ptr = line start (pre-shift content)
  TAX
  BEQ .redist_copy             ; Width 0: no spaces
.write_spaces:
  LDA #' '
  STA (JUMP_TARGET16),Y        ; (Y = 0 from shift_line_width)
  INY
  DEX
  BNE .write_spaces
.redist_copy:
  JSR shift_count_line         ; (keeps Y, the width)
  ; Advance write ptr by width
  TYA
  ADDA16 JUMP_TARGET16
  JSR copy_line_to_nl
  TST16 BUF_TEMP16
  BNE .redist

  ; A batch's last pair starts on the first non-blank as the earlier
  ; ones left it: moved right by their width if they shifted the line
  LDA NORMAL_TEMP
  BEQ .no_col_adj
  LDA SHIFT_PREV_WIDTH
  ADDA16 CURSOR_COL16
.no_col_adj:

  ; Record undo: u removes the recorded per-line widths via unindent
  LDA #UNDO_INDENT
  JMP shift_finish
.noop:
  LDA #UNDO_INDENT
  JMP shift_record

; Remove up to BUF_DELTA leading spaces from each line of a range
; (see contract above).  Per-line removal counts are recorded to
; UNDO_DATA_BUF so undo can restore exactly what was removed.
remove_spaces_core:
  JSR shift_prologue

.unindent_loop:
  JSR shift_line_start         ; BUF_PTR16 = line start

  ; Count leading spaces up to BUF_DELTA
  LDY #0
.count_spaces:
  CPY BUF_DELTA
  BCS .have_spaces
  LDA (BUF_PTR16),Y
  CMP #' '
  BNE .have_spaces
  INY
  BNE .count_spaces            ; Always taken (Y <= BUF_DELTA)
.have_spaces:
  ; Y = spaces to remove for this line (0..BUF_DELTA)

  ; Record the last logical op's removal (small ranges only):
  ; removed minus what earlier ops of the batch took, floored at 0
  LDA SHIFT_LINES16 + 1
  BNE .no_record
  TYA
  SEC
  SBC SHIFT_PREV_WIDTH                ; minus prev-ops width
  BCS .record_ok
  LDA #0
.record_ok:
  LDX SHIFT_LINE_IDX
  STA UNDO_DATA_BUF,X
.no_record:

  JSR shift_count_line         ; (keeps Y)
  TST16 COUNT16
  BEQ .next                    ; Nothing removed yet: the line stays put

  ; Advance BUF_PTR16 past leading spaces
  TYA
  JSR ptr_add_a

  ; Copy remaining line (including newline) to write ptr
  JSR copy_line_to_nl

.next:
  TST16 BUF_TEMP16
  BNE .unindent_loop

  ; If nothing was removed: an empty change (no MODIFIED, no repaint)
  TST16 COUNT16
  BEQ .noop

  ; Single shift left: close the gap after processed range
  CP16 JUMP_TARGET16, BUF_PTR16
  CP16 COUNT16, BUF_LEN16
  JSR buf_shift_left_16

  ; A batch's last pair starts on the first non-blank as the earlier
  ; ones left it: moved left by what they removed from the line (up to
  ; SHIFT_PREV_WIDTH; a batch starts below col 256, on one line)
  LDA SHIFT_PREV_WIDTH
  CMP NORMAL_TEMP
  BCC .prev_took
  LDA NORMAL_TEMP
.prev_took:
  STA NORMAL_TEMP
  LDA CURSOR_COL16
  SEC
  SBC NORMAL_TEMP
  BCS .col_ok
  LDA #0                       ; (the first non-blank of a line of spaces)
.col_ok:
  STA CURSOR_COL16

  ; Record undo: u re-inserts the recorded per-line counts (the last
  ; logical op's: if earlier batch ops took it all, an empty change, as
  ; the no-op << the last pair is when typed singly)
  LDA #UNDO_UNINDENT
  JMP shift_finish
.noop:
  LDA #UNDO_UNINDENT
  JMP shift_record

; A = width to insert on the line starting at (BUF_PTR16), line index
; SHIFT_LINE_IDX: the recorded width in data mode, else 0 for an empty
; line and BUF_DELTA otherwise.  Returns Y = 0.  Clobbers X.
shift_line_width:
  LDY #0
  LDA SHIFT_MODE
  BEQ .const
  LDX SHIFT_LINE_IDX
  LDA UNDO_DATA_BUF,X
  RTS
.const:
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .empty
  LDA BUF_DELTA
  RTS
.empty:
  TYA
  RTS

; Copy bytes from (BUF_PTR16) to (JUMP_TARGET16) until '\n' is copied.
; Advances both pointers past the copied data.
; Clobbers: A, Y
copy_line_to_nl:
  LDY #0
  LDA (BUF_PTR16),Y
  STA (JUMP_TARGET16),Y
  INC16 BUF_PTR16
  INC16 JUMP_TARGET16
  CMP #'\n'
  BNE copy_line_to_nl
  RTS

; Per-line bookkeeping for the core loops (Y = this line's width or
; removal, kept): remember it in NORMAL_TEMP for the column adjust (only
; a batch uses it, and a batch is on one line, the cursor's), add it to
; COUNT16 (at most 1023 lines of 2 or one line of 66: no carry out),
; step the line index and the line iterator (LINE_LEN16) and count the
; line off.  Returns Z set when the range is done (BUF_TEMP16 = 0;
; shift_prologue has returned early for an empty range, so the loops
; test at the bottom).  Clobbers A.
shift_count_line:
  STY NORMAL_TEMP
  TYA
  CLC
  ADC COUNT16
  STA COUNT16
  BCC .counted
  INC COUNT16 + 1
.counted:
  INC SHIFT_LINE_IDX
  INC16 LINE_LEN16
  ; fall through

; BUF_TEMP16 -= 1; Z = 1 if it reached 0.  Clobbers A
dec_buf_temp16:
  DEC16 BUF_TEMP16
  TST16 BUF_TEMP16
  RTS

; --- Dollar and zero motion operations: D, d$, y$, d0, y0 (C in
; normal_edit.asm shares dollar_range_setup) ---

; y0 / d0: yank / delete from BOL to the cursor (count ignored).  The
; cursor goes to col 0, where the range starts, as in vim
do_d_zero:
  LDX #OP_DELETE
  BNE zero_col_op             ; Always
do_y_zero:
  LDX #OP_YANK
zero_col_op:
  CP16 CURSOR_COL16, BUF_LEN16 ; BUF_LEN16 = bytes from BOL to cursor
  ORA BUF_LEN16
  BNE .range
  ; Already at col 0: y0 yanks the empty range, d0 is an empty change,
  ; as in vim
  TXA
  BEQ .range
  JSR undo_record_empty
  BEQ .done                   ; Always
.range:
  LDA #0
  STA_LH16 CURSOR_COL16       ; Operate forward from col 0
  TXA
  JSR apply_char_operator
.done:
  JMP clear_count

; y$: yank from the cursor to EOL (count lines)
do_y_dollar:
  LDX #OP_YANK
  BEQ dollar_op               ; Always taken (OP_YANK = 0)

; D and d$: delete from the cursor to EOL (count lines)
normal_delete_to_eol:
  LDX #OP_DELETE
  ; fall through

; Apply operator X to the $ range, if any (vi's linewise rule for a
; delete: op_lines)
dollar_op:
  STX NORMAL_TEMP             ; Save operator
  JSR get_count_clamp_lines   ; (a count on the last line ends it)
  JSR dollar_range_setup
  BCC .range
  LDA NORMAL_TEMP
  BNE .done                   ; Nothing to do (y$ yanks the empty range,
.range:                       ; as in vim)
  LDA NORMAL_TEMP
  JSR op_lines                ; (linewise: the command ends there)
  LDA NORMAL_TEMP
  JSR apply_char_operator
.done:
  JMP clear_count

; Shared $-range setup for D, d$, y$ and C, after get_count_clamp_lines
; (the count stops at the last line, and on the last line a count of 2
; or more ends the command, as in vim): BUF_LEN16 = bytes from the
; cursor to the end of the count-th line (from an empty line too, as in
; vi), carry set if there are none: the start of the line after the
; range (the end of the text after the last line), less its newline,
; less the cursor's address.  Input: BUF_TEMP16 = count.  Preserves
; NORMAL_TEMP.  Clobbers A, X, Y, BUF_PTR16, BUF_SRC16
dollar_range_setup:
  JSR get_cursor_src          ; BUF_SRC16 = the cursor's address
  CLC
  LDA FILE_LINE16
  ADC BUF_TEMP16
  TAY
  LDA FILE_LINE16 + 1
  ADC BUF_TEMP16 + 1
  TAX
  TYA
  JSR buf_get_line_ptr        ; The line after the range
  CLC                         ; (The borrow drops the newline)
  SBC16 BUF_PTR16, BUF_SRC16, BUF_LEN16
  JMP range_epilogue

; --- Word operations: delete, change ---
; All word operations are thin wrappers: they pass the range routine in
; A/X (low/high) and the operator in Y to word_op_forward.  yw, ye and yb
; (normal_move.asm) enter at word_w_op, word_end_op and word_b_op.

; dw: delete N words forward
do_dw:
  LDY #OP_DELETE
word_w_op:
  LDA #<compute_multiline_word_range_forward
  LDX #>compute_multiline_word_range_forward
  BNE word_op_forward         ; Always taken (code starts at $0400)

; cw: change N words forward (vi cw = ce range)
do_cw:
  LDY #OP_CHANGE
  LDA #<compute_multiline_cw_range_forward
  LDX #>compute_multiline_cw_range_forward
  BNE word_op_forward         ; Always taken (code starts at $0400)

; cb: change N words backward
do_cb:
  LDY #OP_CHANGE
  BNE word_b_op               ; Always taken (OP_CHANGE = 2)

; db: delete N words backward
do_db:
  LDY #OP_DELETE
word_b_op:
  LDA #<compute_multiline_word_range_backward
  LDX #>compute_multiline_word_range_backward
  BNE word_op_forward         ; Always taken (code starts at $0400)

; de: delete to end of N words forward
do_de:
  LDY #OP_DELETE
  BNE word_end_op             ; Always taken (OP_DELETE = 1)

; ce: change to end of N words forward
do_ce:
  LDY #OP_CHANGE
  ; fall through
word_end_op:
  LDA #<compute_multiline_word_end_range_forward
  LDX #>compute_multiline_word_end_range_forward
  ; fall through into word_op_forward

; --- Shared word operation helpers ---

; Word operation: delete, yank or change over the range of a w, b or e
; motion from the cursor (b's range starts where b goes: the cursor
; moves there).
; Input: A/X = range computation function (low/high)
;        Y = operator (OP_DELETE, OP_YANK, OP_CHANGE)
; Handles: get_count, range computation, vi's linewise rules (op_lines),
;          apply_char_operator, clamp, clear_count.  From an empty line
;          the ranges go on to the next line.
; OP_CHANGE bails into insert mode on an empty range.
word_op_forward:
  STA JUMP_TARGET16
  STX JUMP_TARGET16 + 1
  TYA
  PHA                          ; Save operator
  JSR get_count_x              ; X = N (capped at 255)
  JSR word_op_call_range       ; BUF_LEN16 = range
  PLA                          ; A = operator
  JSR op_lines                 ; (linewise: the command ends there)
  BCC .range
  LDA NORMAL_TEMP
  BNE word_op_bail             ; Nothing to operate on (a yank takes
.range:                        ; the empty range, as in vim)
  LDA NORMAL_TEMP              ; A = operator
  JSR apply_char_operator      ; (c enters insert mode)
  JMP clamp_for_mode

; Shared bail: c enters insert mode (an empty change)
word_op_bail:
  CMP #OP_CHANGE
  BEQ .bail_insert
  JMP clear_count

.bail_insert:
  JMP sub_change_insert

; JSR here calls the range routine in JUMP_TARGET16 (word_op_forward)
word_op_call_range:
  JMP (JUMP_TARGET16)
