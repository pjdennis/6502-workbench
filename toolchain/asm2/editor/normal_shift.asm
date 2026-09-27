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
;
; On change the cores set MODIFIED and render flags (RF_RANGE partial
; repaint when possible, else RF_FULL), and record undo for ranges up to
; 255 lines: UNDO_LINE16, UNDO_COL16 (the cursor column, moved as a
; batch's earlier pairs moved the first non-blank), UNDO_RANGE_LINES16
; and the per-line widths in UNDO_DATA_BUF (indexed by SHIFT_LINE_IDX
; while they run).  Undo covers the last >> / <<, one INDENT_WIDTH step:
; batched pairs multiply W, but u behaves as if the keys ran separately.
; On no-op (nothing inserted/removed) they leave MODIFIED and RENDER_FLAG
; untouched so the frame is a pure cursor/status update.

; (zero-page variables: zp.asm)

; Scratch the cores reuse while they run (aliases)
SHIFT_LINE_IDX   = UNDO_JOIN_COUNT ; line index into UNDO_DATA_BUF
SHIFT_RECORDED   = SHIFT_MODE      ; remove core: nonzero once a last-op removal is recorded

INDENT_WIDTH = 2

; >> and <<: the cursor ends on the first non-blank, as in vim
do_indent:
  JSR shift_normal_setup
  JSR insert_spaces_core
  JMP first_nonblank_clear

do_unindent:
  JSR shift_normal_setup
  JSR remove_spaces_core
  JMP first_nonblank_clear

; Shared >> / << entry setup.
; Clamps the line count and computes BUF_DELTA = INDENT_WIDTH * (1 +
; BATCH_EXTRA).  A count means lines and a repeated pair width, so the
; typed-ahead pairs merge (multiplying the width) only when no count was
; typed: 3>>>> is 3>> then >>.  The cursor goes where vim starts the
; operator, the column u returns to: over two or more lines the cursor,
; on one line the first non-blank if it is further left.  A batch's
; later pairs each start on the first non-blank the pair before left
; (the cores move it as the earlier pairs moved the text).
shift_normal_setup:
  JSR get_count_clamp_lines    ; BUF_TEMP16 = line count
  LDX #0                       ; No pairs taken
  LDA COUNT16
  ORA COUNT16 + 1
  BNE .counted
  JSR batch_pending_pairs      ; X = BATCH_EXTRA
.counted:
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

; Common core prologue: clear undo, save the range size for undo
; recording, zero the per-core accumulators, pre-compute the range's
; current screen rows for the $0B render path, and set the line iterator
; (LINE_LEN16) to the range start.  The core loops test at the bottom,
; so an empty range (BUF_TEMP16 = 0: >> / << after a defect has left the
; cursor past the last line) returns from the core itself, a no-op as
; before.
shift_prologue:
  JSR undo_clear
  CP16 BUF_TEMP16, UNDO_RANGE_LINES16
  CP16 FILE_LINE16, LINE_LEN16
  LDA #0
  STA COUNT16                  ; COUNT16 = total shift/removal
  STA COUNT16 + 1
  STA SHIFT_LINE_IDX           ; Line index for UNDO_DATA_BUF
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

; Record undo (A = type) unless the range was too big for undo data,
; then fall through to the render epilogue.
shift_finish:
  LDX UNDO_RANGE_LINES16 + 1
  BNE shift_set_render         ; Big range: not undoable
  STA UNDO_TYPE
  CP16 FILE_LINE16, UNDO_LINE16
  CP16 CURSOR_COL16, UNDO_COL16

; Common core epilogue for a successful change: set MODIFIED and pick the
; render level.  Partial repaint ($0B) requires pre-computed screen rows
; (render derives the range's screen position from the cursor, which is
; on its first line).
shift_set_render:
  JSR set_modified
  LDA DELETE_SCREEN_ROWS
  BEQ .full
  LDA UNDO_RANGE_LINES16
  STA INSERT_LINE_COUNT        ; range line count for render
  LDA #RF_RANGE
  STA RENDER_FLAG              ; range repaint
  RTS
.full:
  LDA #RF_FULL
  STA RENDER_FLAG
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
  CP16 UNDO_RANGE_LINES16, BUF_TEMP16 ; Line count again for redistribute

  ; Nothing to insert (all lines empty): pure no-op
  TST16 COUNT16
  BEQ shift_noop

  ; Single buffer shift right at first line start
  CP16 COUNT16, BUF_LEN16
  JSR get_current_line_ptr
  JSR buf_shift_right_16
  BCS shift_full               ; Buffer full: nothing changed

  ; --- Redistribute: write per-line spaces, copy line content down ---
  CP16 BUF_PTR16, JUMP_TARGET16 ; write ptr = first line start
  CLC
  ADC16 BUF_PTR16, BUF_LEN16, BUF_PTR16 ; read ptr = start + total shift
  LDA #0
  STA SHIFT_LINE_IDX          ; Reset line index

.redist:
  JSR shift_line_width         ; read ptr = line start (pre-shift content)
  TAX
  BEQ .redist_copy             ; Width 0: no spaces
.write_spaces:
  LDA #' '
  STA (JUMP_TARGET16),Y        ; (Y = 0 from shift_line_width)
  INY
  DEX
  BNE .write_spaces
  ; Advance write ptr by width
  TYA
  ADDA16 JUMP_TARGET16

.redist_copy:
  JSR copy_line_to_nl

  INC SHIFT_LINE_IDX
  JSR dec_buf_temp16
  BNE .redist

  JSR buf_rebuild_lines

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

; Shared no-op exit: leave MODIFIED/RENDER_FLAG untouched
shift_noop:
  RTS

; Remove up to BUF_DELTA leading spaces from each line of a range
; (see contract above).  Per-line removal counts are recorded to
; UNDO_DATA_BUF so undo can restore exactly what was removed.
remove_spaces_core:
  JSR shift_prologue

  LDA #0
  STA SHIFT_RECORDED               ; Accumulates recorded (last-op) removals

  ; Set write ptr = first line start
  JSR get_current_line_ptr
  CP16 BUF_PTR16, JUMP_TARGET16

.unindent_loop:
  ; Get line start from LINE_TBL (still valid, no shifts yet)
  LDAX16 LINE_LEN16
  JSR buf_get_line_ptr         ; BUF_PTR16 = line start

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
  LDA UNDO_RANGE_LINES16 + 1
  BNE .no_record
  TYA
  SEC
  SBC SHIFT_PREV_WIDTH                ; minus prev-ops width
  BCS .record_ok
  LDA #0
.record_ok:
  LDX SHIFT_LINE_IDX
  STA UNDO_DATA_BUF,X
  ORA SHIFT_RECORDED
  STA SHIFT_RECORDED               ; nonzero if any last-op removal recorded
.no_record:

  JSR shift_count_line         ; (keeps Y)

  ; Advance BUF_PTR16 past leading spaces
  TYA
  JSR ptr_add_a

  ; Copy remaining line (including newline) to write ptr
  JSR copy_line_to_nl

  TST16 BUF_TEMP16
  BNE .unindent_loop

  ; If nothing was removed, pure no-op (no MODIFIED, no repaint)
  TST16 COUNT16
  BEQ shift_noop

  ; Single shift left: close the gap after processed range
  CP16 JUMP_TARGET16, BUF_PTR16
  CP16 COUNT16, BUF_LEN16
  JSR buf_shift_left_16
  JSR buf_rebuild_lines

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

  ; Record undo: u re-inserts the recorded per-line counts.  If the
  ; last logical op removed nothing (earlier batch ops took it all),
  ; there is nothing to undo -- matches unbatched no-op << behavior.
  LDA SHIFT_RECORDED
  BEQ .no_undo
  LDA #UNDO_UNINDENT
  JMP shift_finish
.no_undo:
  JMP shift_set_render

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

; --- Dollar and zero motion operations: D, d$, y$, d0, y0 (C in
; normal_edit.asm shares dollar_range_setup) ---

; y0 / d0: yank / delete from BOL to the cursor (count ignored).  y0
; leaves the cursor where it was; d0 leaves it at col 0.
do_y_zero:
  PUSH16 CURSOR_COL16
  LDX #OP_YANK
  JSR zero_col_op             ; (ends with clear_count)
  POP16 CURSOR_COL16
  RTS
do_d_zero:
  LDX #OP_DELETE
zero_col_op:
  CP16 CURSOR_COL16, BUF_LEN16 ; BUF_LEN16 = bytes from BOL to cursor
  ORA BUF_LEN16
  BEQ .done                   ; Already at col 0: nothing to do
  LDA #0
  STA_LH16 CURSOR_COL16       ; Operate forward from col 0
  TXA
  JSR apply_char_operator
.done:
  JMP clear_count

; Shared $-range setup for D, d$, y$ and C: carry set if the cursor is
; not on a char (empty line); else carry clear and BUF_LEN16 = bytes
; from the cursor to the end of the count-th line
dollar_range_setup:
  JSR check_cursor_in_line
  BCS .ret
  JSR get_count
  JSR compute_dollar_range
  CLC
.ret:
  RTS

; y$: yank from the cursor to EOL (count lines)
do_y_dollar:
  LDX #OP_YANK
  BEQ dollar_op               ; Always taken (OP_YANK = 0)

; d$: delete from the cursor to EOL (count lines), repainting the whole
; line (D below repaints from the cursor)
do_d_dollar:
  LDX #OP_DELETE
  BNE dollar_op               ; Always taken (OP_DELETE = 1)

; D: delete from the cursor to EOL (count lines)
normal_delete_to_eol:
  JSR set_render_from_cursor
  LDX #OP_DELETE
  ; fall through

; Apply operator X to the $ range, if any
dollar_op:
  TXA
  PHA                         ; Save operator
  JSR dollar_range_setup
  PLA
  BCS .done                   ; Empty line: nothing to do
  JSR apply_char_operator
.done:
  JMP clear_count

; Compute byte range for $ motion with count
; Input: BUF_TEMP16 = count (from get_count), LINE_LEN16 set by check_cursor_in_line
; Output: BUF_LEN16 = byte count from cursor to end of range
; For count=1: BUF_LEN16 = LINE_LEN16 - CURSOR_COL16
; For count>1: adds newline + line_length for each additional line
compute_dollar_range:
  ; Start with current line remainder
  SEC
  SBC16 LINE_LEN16, CURSOR_COL16, BUF_LEN16

  ; Check if count > 1
  LDA BUF_TEMP16 + 1
  BNE .multiline              ; count > 255
  LDA BUF_TEMP16
  CMP #2
  BCC .done                   ; count = 1, done

.multiline:
  ; remaining = count - 1
  JSR dec_buf_temp16
  ; next_line = FILE_LINE16 + 1
  CLC
  ADCI16 FILE_LINE16, 1, COUNT16

.add_line:
  ; Check bounds: if next_line >= LINE_COUNT16, stop
  CMP16 COUNT16, LINE_COUNT16
  BCS .done

  ; Add 1 for the newline
  INC16 BUF_LEN16

  ; Get length of this line
  LDAX16 COUNT16
  JSR buf_get_line_len
  ; A = low byte, X = high byte of line length
  CLC
  ADC BUF_LEN16
  STA BUF_LEN16
  TXA
  ADC BUF_LEN16 + 1
  STA BUF_LEN16 + 1

  ; Next line
  INC16 COUNT16
  JSR dec_buf_temp16
  BNE .add_line

.done:
  RTS

; --- Word operations: delete, change ---
; All word operations are thin wrappers: the forward ones pass the range
; routine in A/X (low/high) and the operator in Y to word_op_forward, the
; backward ones the operator in A to word_op_backward.  yw, ye and yb
; (normal_move.asm) enter at word_w_op, word_end_op and word_op_backward.

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

; Forward word operation: handles delete, yank, and change for w/e motions.
; Input: A/X = range computation function (low/high)
;        Y = operator (OP_DELETE, OP_YANK, OP_CHANGE)
; Handles: get_count, check_cursor_in_line,
;          range computation, apply_char_operator, clamp, clear_count.
; OP_CHANGE bails into insert mode on empty line or failed range.
word_op_forward:
  STA JUMP_TARGET16
  STX JUMP_TARGET16 + 1
  TYA
  PHA                          ; Save operator
  JSR get_count_x              ; BUF_TEMP16 = N (capped at 255)
  JSR check_cursor_in_line
  BCS word_op_bail

  JSR set_render_from_cursor
  LDX BUF_TEMP16
  JSR word_op_call_range       ; BUF_LEN16 = range
  BCS word_op_bail

; Shared success tail (word_op_backward jumps here too;
; stack: return addr + pushed operator in both routines)
word_op_tail:
  PLA                          ; A = operator
  CMP #OP_CHANGE
  PHA                          ; Re-save (A preserved, flags from CMP)
  BEQ word_op_do_change
  ; OP_DELETE or OP_YANK
  JSR apply_char_operator
  PLA
  JMP clamp_and_clear_count

word_op_do_change:
  PLA                          ; A = OP_CHANGE
  JMP apply_char_operator      ; Enters insert mode + clear_count

; Shared bail (word_op_backward branches here too)
word_op_bail:
  PLA                          ; Recover operator
  CMP #OP_CHANGE
  BEQ .bail_insert
  JMP clear_count

.bail_insert:
  JMP enter_insert_mode

; JSR here calls the range routine in JUMP_TARGET16 (word_op_forward)
word_op_call_range:
  JMP (JUMP_TARGET16)

; cb: change N words backward
do_cb:
  LDA #OP_CHANGE
  BNE word_op_backward        ; Always taken (OP_CHANGE = 2)

; db: delete N words backward
do_db:
  LDA #OP_DELETE
  ; fall through

; Backward word operation: handles delete, yank, and change for b motion.
; Input: A = operator (OP_DELETE, OP_YANK, OP_CHANGE)
; Uses compute_multiline_word_range_backward directly.
; Handles: get_count, file-start bail,
;          range computation, apply_char_operator, clamp, clear_count.
; OP_CHANGE bails into insert mode at file start or failed range.
word_op_backward:
  PHA                          ; Save operator
  JSR get_count_x              ; BUF_TEMP16 = N (capped at 255)
  ; Bail at file start (col 0 AND line 0)
  TST16 CURSOR_COL16
  BNE .ok
  TST16 FILE_LINE16
  BEQ word_op_bail
.ok:
  LDX BUF_TEMP16
  JSR compute_multiline_word_range_backward
  BCS word_op_bail
  JSR set_render_from_cursor
  JMP word_op_tail             ; Shared success tail (in word_op_forward)
