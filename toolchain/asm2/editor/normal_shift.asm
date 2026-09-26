; Normal-mode shift and span operations: >> / << (with the shared
; insert/remove space cores used by range commands and undo), plus
; line-content helpers and dollar/word operator commands.  Split from
; normal_edit.asm; see that file for paste/join/substitute/replace.


; --- Indent (>>) and unindent (<<) ---
;
; Both are built on two shared cores that operate on an arbitrary line
; range: insert_spaces_core (add leading spaces) and remove_spaces_core
; (strip leading spaces).  The cores are also used by the :[range]> and
; :[range]< commands and by undo/redo of these operations.
;
; Core input contract:
;   UNDO_LINE16  = first line of the range
;   BUF_TEMP16   = number of lines in the range (0 = do nothing)
;   BUF_DELTA    = space width W (insert per non-empty line / max removal)
;   SHIFT_MODE   = insert core only: 0 = constant width W per non-empty
;                  line; $FF = per-line widths from UNDO_DATA_BUF (undo)
;
; On change the cores set MODIFIED and render flags ($0B partial repaint
; when possible, else $FF), and record undo (ranges up to 255 lines).
; On no-op (nothing inserted/removed) they leave MODIFIED and RENDER_FLAG
; untouched so the frame is a pure cursor/status update.

  .zeropage

SHIFT_MODE: .byte       ; insert_spaces_core width source (0=const, $FF=data)
SHIFT_UNDO_WIDTH: .byte ; width of the LAST logical op for undo recording
                        ; (batched pairs multiply BUF_DELTA, but undo must
                        ; behave as if the keys ran separately, so undo
                        ; covers only the final op's contribution)

  .code

INDENT_WIDTH = 2

do_indent:
  JSR shift_normal_setup
  JSR insert_spaces_core
  JMP clear_count

do_unindent:
  JSR shift_normal_setup
  JSR remove_spaces_core
  JMP clear_count

; Shared >> / << entry setup.
; Computes BUF_DELTA = INDENT_WIDTH * (1 + BATCH_EXTRA) (batched pairs
; multiply the width), removes the batch extras that batch_pending_pairs
; added to COUNT16 (for >> the count means lines, not repeats), clamps the
; line count, and sets the range start to the cursor line.
shift_normal_setup:
  LDA BATCH_EXTRA
  CLC
  ADC #1                       ; A = repeat count (1 + extra pairs)
  ASL                          ; *INDENT_WIDTH (hardcoded: ASL assumes INDENT_WIDTH = 2)
  STA BUF_DELTA                ; BUF_DELTA = INDENT_WIDTH * repeat count
  LDA #INDENT_WIDTH
  STA SHIFT_UNDO_WIDTH         ; undo = last >> / << only
  LDA BATCH_EXTRA
  BEQ .no_count_fix
  LDA COUNT16
  SEC
  SBC BATCH_EXTRA
  STA COUNT16
  LDA COUNT16 + 1
  SBC #0
  STA COUNT16 + 1
.no_count_fix:
  JSR get_count_clamp_lines    ; BUF_TEMP16 = line count
  CP16 FILE_LINE16, UNDO_LINE16
  LDA #0
  STA SHIFT_MODE
  RTS

; Common core prologue: clear undo, save range/cursor for undo recording,
; zero the per-core accumulators, pre-compute the range's current screen
; rows for the $0B render path, and set the line iterator (LINE_LEN16) to
; the range start.  The core loops test at the bottom, so an empty range
; (BUF_TEMP16 = 0: >> / << after a defect has left the cursor past the
; last line) returns from the core itself, a no-op as before.
shift_prologue:
  JSR undo_clear
  CP16 BUF_TEMP16, UNDO_PASTE_COUNT16
  CP16 CURSOR_COL16, UNDO_COL16
  CP16 UNDO_LINE16, LINE_LEN16
  LDA #0
  STA NORMAL_TEMP              ; Cursor line width/removal (column adjust)
  STA COUNT16                  ; COUNT16 = total shift/removal
  STA COUNT16 + 1
  STA UNDO_JOIN_COUNT          ; Line index for UNDO_DATA_BUF
  STA DELETE_SCREEN_ROWS       ; 0 = no partial repaint (fall back to full)
  LDA BUF_TEMP16 + 1
  BNE .done                    ; > 255 lines: full repaint, no undo
  CP16 UNDO_LINE16, RENDER_LINE16
  LDA BUF_TEMP16
  BEQ .empty
  JMP compute_delete_screen_rows
.empty:
  PLA                          ; Drop the return into the core: return
  PLA                          ; to the core's caller
.done:
  RTS

; Record undo (A = type) unless the range was too big for undo data,
; then fall through to the render epilogue.
shift_finish:
  LDX UNDO_PASTE_COUNT16 + 1
  BNE shift_set_render         ; Big range: not undoable
  STA UNDO_TYPE
  LDA SHIFT_UNDO_WIDTH
  STA UNDO_JOIN_COUNT          ; Width of the last logical op (for undo)

; Common core epilogue for a successful change: set MODIFIED and pick the
; render level.  Partial repaint ($0B) requires pre-computed screen rows
; and the cursor sitting on the first line of the range (render derives
; the range's screen position from the cursor).
shift_set_render:
  LDA #$FF
  STA MODIFIED
  LDA DELETE_SCREEN_ROWS
  BEQ .full
  CMP16 FILE_LINE16, UNDO_LINE16
  BNE .full
  LDA UNDO_PASTE_COUNT16
  STA INSERT_LINE_COUNT        ; range line count for render
  LDA #$0B
  STA RENDER_FLAG              ; range repaint
  RTS
.full:
  LDA #$FF
  STA RENDER_FLAG
  RTS

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
  CP16 UNDO_PASTE_COUNT16, BUF_TEMP16 ; Line count again for redistribute

  ; Nothing to insert (all lines empty): pure no-op
  TST16 COUNT16
  BEQ shift_noop

  ; Single buffer shift right at first line start
  CP16 COUNT16, BUF_LEN16
  LDAX16 UNDO_LINE16
  JSR buf_get_line_ptr
  JSR buf_shift_right_16
  BCS shift_noop               ; Buffer full: nothing changed

  ; --- Redistribute: write per-line spaces, copy line content down ---
  CP16 BUF_PTR16, JUMP_TARGET16 ; write ptr = first line start
  CLC
  ADC16 BUF_PTR16, BUF_LEN16, BUF_PTR16 ; read ptr = start + total shift
  LDA #0
  STA UNDO_JOIN_COUNT          ; Reset line index

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
  CLC
  ADCA16 JUMP_TARGET16, JUMP_TARGET16

.redist_copy:
  JSR copy_line_to_nl

  INC UNDO_JOIN_COUNT
  DEC16 BUF_TEMP16
  TST16 BUF_TEMP16
  BNE .redist

  JSR buf_rebuild_lines

  ; Adjust cursor column if the cursor's line was indented
  LDA NORMAL_TEMP
  BEQ .no_col_adj
  CLC
  ADCA16 CURSOR_COL16, CURSOR_COL16
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
  STA SHIFT_MODE               ; Accumulates recorded (last-op) removals
  ; Removal attributable to earlier ops of a batch (per line)
  LDA BUF_DELTA
  SEC
  SBC SHIFT_UNDO_WIDTH
  STA BUF_LEN16                ; BUF_LEN16 = prev-ops width (temp)

  ; Set write ptr = first line start
  LDAX16 UNDO_LINE16
  JSR buf_get_line_ptr
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
  LDA UNDO_PASTE_COUNT16 + 1
  BNE .no_record
  TYA
  SEC
  SBC BUF_LEN16                ; minus prev-ops width
  BCS .record_ok
  LDA #0
.record_ok:
  LDX UNDO_JOIN_COUNT
  STA UNDO_DATA_BUF,X
  ORA SHIFT_MODE
  STA SHIFT_MODE               ; nonzero if any last-op removal recorded
.no_record:

  JSR shift_count_line         ; (keeps Y)

  ; Advance BUF_PTR16 past leading spaces
  TYA
  CLC
  ADCA16 BUF_PTR16, BUF_PTR16

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

  ; Cursor adjustment: subtract actual spaces removed, clamp to 0
  LDA NORMAL_TEMP
  BEQ .no_cursor_adj
  LDA CURSOR_COL16
  SEC
  SBC NORMAL_TEMP
  STA CURSOR_COL16
  LDA CURSOR_COL16 + 1
  SBC #0
  STA CURSOR_COL16 + 1
  BCS .col_ok
  LDA #0
  STA_LH16 CURSOR_COL16
.col_ok:
  JSR clamp_cursor_col
.no_cursor_adj:

  ; Record undo: u re-inserts the recorded per-line counts.  If the
  ; last logical op removed nothing (earlier batch ops took it all),
  ; there is nothing to undo -- matches unbatched no-op << behavior.
  LDA SHIFT_MODE
  BEQ .no_undo
  LDA #UNDO_UNINDENT
  JMP shift_finish
.no_undo:
  JMP shift_set_render

; A = width to insert on the line starting at (BUF_PTR16), line index
; UNDO_JOIN_COUNT: the recorded width in data mode, else 0 for an empty
; line and BUF_DELTA otherwise.  Returns Y = 0.  Clobbers X.
shift_line_width:
  LDY #0
  LDA SHIFT_MODE
  BEQ .const
  LDX UNDO_JOIN_COUNT
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
; removal, kept): remember it for the cursor line's column adjust, add it
; to COUNT16, step the line index and the line iterator (LINE_LEN16) and
; count the line off.  Returns Z set when the range is done
; (BUF_TEMP16 = 0; shift_prologue has returned early for an empty range,
; so the loops test at the bottom).  Clobbers A.
shift_count_line:
  CMP16 LINE_LEN16, FILE_LINE16
  BNE .not_cursor
  STY NORMAL_TEMP
.not_cursor:
  TYA
  CLC
  ADCA16 COUNT16, COUNT16
  INC UNDO_JOIN_COUNT
  INC16 LINE_LEN16
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
  CP16 CURSOR_COL16, RENDER_FROM_COL16
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
  SEC
  SBCI16 BUF_TEMP16, 1, BUF_TEMP16
  ; next_line = FILE_LINE16 + 1
  CLC
  ADCI16 FILE_LINE16, 1, COUNT16

.add_line:
  ; Check bounds: if next_line >= LINE_COUNT16, stop
  CMP16 COUNT16, LINE_COUNT16
  BCS .done

  ; Add 1 for the newline
  CLC
  ADCI16 BUF_LEN16, 1, BUF_LEN16

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
  DEC16 BUF_TEMP16
  TST16 BUF_TEMP16
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
; Handles: get_count, check_cursor_in_line, batch check (OP_DELETE only),
;          range computation, apply_char_operator, clamp, clear_count.
; OP_CHANGE bails into insert mode on empty line or failed range.
word_op_forward:
  STA JUMP_TARGET16
  STX JUMP_TARGET16 + 1
  TYA
  PHA                          ; Save operator
  JSR get_count                ; BUF_TEMP16 = N
  JSR check_cursor_in_line
  BCS word_op_bail

  CP16 CURSOR_COL16, RENDER_FROM_COL16

  ; Check for batched delete (OP_DELETE with BATCH_EXTRA > 0)
  TSX
  LDA $0101,X                  ; Peek operator from stack
  CMP #OP_DELETE
  BNE .non_batched
  LDA BATCH_EXTRA
  BNE word_op_fwd_batched

.non_batched:
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

word_op_fwd_batched:
  PLA                          ; Discard operator (always DELETE)
  JSR batched_word_delete_fwd
  JMP clamp_and_clear_count

; Shared bail (word_op_backward branches here too)
word_op_bail:
  PLA                          ; Recover operator
  CMP #OP_CHANGE
  BEQ .bail_insert
  JMP clear_count

.bail_insert:
  JMP enter_insert_mode_render

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
; Handles: get_count, file-start bail, batch check (OP_DELETE only),
;          range computation, apply_char_operator, clamp, clear_count.
; OP_CHANGE bails into insert mode at file start or failed range.
word_op_backward:
  PHA                          ; Save operator
  JSR get_count                ; BUF_TEMP16 = N
  ; Bail at file start (col 0 AND line 0)
  TST16 CURSOR_COL16
  BNE .ok
  TST16 FILE_LINE16
  BEQ word_op_bail
.ok:
  ; Check for batched delete (OP_DELETE with BATCH_EXTRA > 0)
  TSX
  LDA $0101,X                  ; Peek operator from stack
  CMP #OP_DELETE
  BNE .non_batched
  LDA BATCH_EXTRA
  BNE .batched

.non_batched:
  LDX BUF_TEMP16
  JSR compute_multiline_word_range_backward
  BCS word_op_bail
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  JMP word_op_tail             ; Shared success tail (in word_op_forward)

.batched:
  PLA                          ; Discard operator (always DELETE)
  JSR batched_word_delete_bwd
  JMP clamp_and_clear_count

; --- Batched word delete helpers ---

; Batched word delete forward (shared by dw and de batched paths)
; Input: JUMP_TARGET16 = range computation function pointer
;        BUF_TEMP16 = N (total word count, >= 2)
; Computes full N-word range, yanks last word only, deletes all in single shift.
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_LEN16, BUF_TEMP16,
;           NORMAL_TEMP, WORD_CLASS, LINE_LEN16
batched_word_delete_fwd:
  ; Save N on stack
  LDA BUF_TEMP16
  PHA

  ; Compute full N-word range
  LDX BUF_TEMP16
  JSR .fwd_call_range          ; BUF_LEN16 = full_range, cursor restored
  BCS .fwd_bail

  ; Save full_range on stack
  PUSH16 BUF_LEN16

  ; Compute (N-1)-word prefix range
  TSX
  LDA $0103,X                  ; Recover N (under 2 bytes of full_range)
  SEC
  SBC #1
  TAX                           ; X = N-1
  JSR .fwd_call_range          ; BUF_LEN16 = prefix_range, cursor restored

  ; Yank last word using buffer pointer arithmetic (no cursor movement)
  ; BUF_LEN16 = prefix_range
  JSR yank_clear
  JSR get_cursor_buf_ptr        ; BUF_PTR16 = cursor buf address

  ; BUF_SRC16 = cursor_buf_ptr + prefix_range = start of last word
  CLC
  ADC16 BUF_PTR16, BUF_LEN16, BUF_SRC16

  ; Recover full_range, discard N
  POP16 BUF_TEMP16              ; BUF_TEMP16 = full_range
  PLA                           ; discard N

  ; last_word_len = full_range - prefix_range
  SEC
  SBC16 BUF_TEMP16, BUF_LEN16, BUF_LEN16  ; BUF_LEN16 = last_word_len

  ; Yank the last word
  JSR yank_add_chars            ; Yank BUF_LEN16 chars from BUF_SRC16

  ; Delete full range at cursor (single shift)
  CP16 BUF_TEMP16, BUF_LEN16   ; BUF_LEN16 = full_range
  JSR delete_at_cursor

  RTS

.fwd_bail:
  PLA                           ; Clean up N
  RTS

.fwd_call_range:
  JMP (JUMP_TARGET16)

; Batched word delete backward (for db batched path)
; Input: BUF_TEMP16 = N (total word count, >= 2)
; Computes full N-word backward range, yanks last word only, deletes all in single shift.
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_LEN16, BUF_TEMP16,
;           NORMAL_TEMP, WORD_CLASS, LINE_LEN16, COUNT16, BATCH_EXTRA
batched_word_delete_bwd:
  ; Save original position on stack
  PUSH16 CURSOR_COL16
  PUSH16 FILE_LINE16

  ; Save N in BATCH_EXTRA (safe across backward range computation)
  LDA BUF_TEMP16
  STA BATCH_EXTRA

  ; Compute N-word backward range
  LDX BUF_TEMP16
  JSR compute_multiline_word_range_backward  ; cursor -> S, BUF_LEN16 = full_range
  BCS .bwd_bail

  ; Save S position and full_range in zero-page temps (safe across backward range)
  CP16 CURSOR_COL16, BUF_TEMP16 ; BUF_TEMP16 = S col
  CP16 FILE_LINE16, BUF_DST16   ; BUF_DST16 = S line
  CP16 BUF_LEN16, COUNT16       ; COUNT16 = full_range

  ; Restore original position for (N-1) computation
  POP16 FILE_LINE16
  POP16 CURSOR_COL16

  ; Compute (N-1)-word backward range
  LDA BATCH_EXTRA
  SEC
  SBC #1
  TAX                            ; X = N-1
  JSR compute_multiline_word_range_backward  ; cursor -> M, BUF_LEN16 = prefix_range

  ; Restore S position (for yank and delete)
  CP16 BUF_TEMP16, CURSOR_COL16 ; Restore S col
  CP16 BUF_DST16, FILE_LINE16   ; Restore S line
  CP16 CURSOR_COL16, RENDER_FROM_COL16

  ; Compute last_word_range = full_range - prefix_range
  SEC
  SBC16 COUNT16, BUF_LEN16, BUF_LEN16  ; BUF_LEN16 = last_word_range

  ; Yank last word at S
  JSR yank_clear
  JSR get_cursor_buf_ptr         ; BUF_PTR16 = buffer address at S
  CP16 BUF_PTR16, BUF_SRC16     ; BUF_SRC16 = yank source
  JSR yank_add_chars             ; Yank last_word_range chars

  ; Delete full range at S (single shift)
  CP16 COUNT16, BUF_LEN16       ; BUF_LEN16 = full_range
  JSR delete_at_cursor

  RTS

.bwd_bail:
  POP16 FILE_LINE16
  POP16 CURSOR_COL16
  RTS
