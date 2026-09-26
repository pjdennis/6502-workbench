; Undo/redo implementation.  Types, state, and the shared data buffer
; live in undo_state.asm (included early so all modules can reference
; them without forward references).

; Clear undo state (called when a new edit supersedes the undo slot)
undo_clear:
  LDA #UNDO_NONE
  STA UNDO_TYPE
  STA UNDO_IS_REDO
  RTS

; Record a char-delete for undo
; Call after the yank, before the delete (undo_delete_at_cursor).
; Saves: type=2, FILE_LINE16, CURSOR_COL16
undo_record_char_delete:
  LDA #UNDO_CHAR
  BNE undo_rec_set           ; Always (UNDO_CHAR != 0)

; Record a line-delete for undo
; Call after yank succeeds, before delete, with BUF_TEMP16 = the line
; count (at most the lines left).
; Saves: type=1, FILE_LINE16 (and CURSOR_COL16, which this type ignores),
; UNDO_EMPTY_LINE bit 7 = the delete empties the buffer
undo_record_line_delete:
  ; The count reaches LINE_COUNT16 only from line 0: every line goes, and
  ; buf_delete_lines leaves a synthetic empty line that undo must remove
  LDA BUF_TEMP16
  CMP LINE_COUNT16
  LDA BUF_TEMP16 + 1
  SBC LINE_COUNT16 + 1
  ROR UNDO_EMPTY_LINE        ; Bit 7 = C = count >= LINE_COUNT16
  LDA #UNDO_LINE
undo_rec_set:
  STA UNDO_TYPE
; Record the cursor position (UNDO_LINE16/UNDO_COL16) and clear the redo
; flag.  Clobbers A (= 0)
undo_record_pos:
  CP16 CURSOR_COL16, UNDO_COL16
  CP16 FILE_LINE16, UNDO_LINE16
  LDA #0
  STA UNDO_IS_REDO
  RTS

; Handle 'u' key: dispatch undo or redo based on UNDO_IS_REDO
; Batching: consume pending 'u' keys. Since u toggles undo/redo,
; odd total = one operation, even total = noop.
undo_handle:
  LDA UNDO_TYPE
  BEQ .done                  ; No undoable operation, no-op
  JSR count_pending_key      ; X = extra u keys in typeahead
  TXA
  LSR
  BCS .done                  ; Odd extras = even total = noop
  ; Per-type handler dispatch via address table (RTS trick): entries are
  ; handler - 1, indexed by UNDO_TYPE (1..13, 0 is filtered above).
  LDA UNDO_TYPE
  ASL                        ; C = 0 (UNDO_TYPE <= 13)
  BIT UNDO_IS_REDO
  BPL .index                 ; Undo pending
  ADC #.redo_table - .table  ; Redo pending: use the redo entries
.index:
  TAX
  LDA .table - 1,X           ; High byte of handler - 1
  PHA
  LDA .table - 2,X           ; Low byte
  PHA
  RTS                        ; Jump to handler
.done:
  JMP clear_count

.table:                              ; Undo handlers
  .word .undo_line - 1               ; 1 UNDO_LINE
  .word .undo_char - 1               ; 2 UNDO_CHAR
  .word .undo_line - 1               ; 3 UNDO_CC
  .word undo_paste_undo - 1          ; 4 UNDO_LINE_PASTE_BELOW
  .word undo_paste_undo - 1          ; 5 UNDO_LINE_PASTE_ABOVE
  .word undo_char_paste_undo - 1     ; 6 UNDO_CHAR_PASTE_BELOW
  .word undo_char_paste_undo - 1     ; 7 UNDO_CHAR_PASTE_ABOVE
  .word undo_join_undo - 1           ; 8 UNDO_JOIN
  .word undo_open_undo - 1           ; 9 UNDO_OPEN
  .word undo_shift_step - 1          ; 10 UNDO_INDENT
  .word undo_shift_step - 1          ; 11 UNDO_UNINDENT
  .word undo_tilde_undo - 1          ; 12 UNDO_TILDE
  .word undo_replace_undo - 1        ; 13 UNDO_REPLACE
.redo_table:                         ; Redo handlers
  .word .redo_line - 1               ; 1 UNDO_LINE
  .word .redo_char - 1               ; 2 UNDO_CHAR
  .word .redo_cc - 1                 ; 3 UNDO_CC
  .word undo_paste_redo - 1          ; 4 UNDO_LINE_PASTE_BELOW
  .word undo_paste_redo - 1          ; 5 UNDO_LINE_PASTE_ABOVE
  .word undo_char_paste_redo - 1     ; 6 UNDO_CHAR_PASTE_BELOW
  .word undo_char_paste_redo - 1     ; 7 UNDO_CHAR_PASTE_ABOVE
  .word undo_join_redo - 1           ; 8 UNDO_JOIN
  .word undo_open_redo - 1           ; 9 UNDO_OPEN
  .word undo_shift_step - 1          ; 10 UNDO_INDENT
  .word undo_shift_step - 1          ; 11 UNDO_UNINDENT
  .word undo_tilde_redo - 1          ; 12 UNDO_TILDE
  .word undo_replace_redo - 1        ; 13 UNDO_REPLACE

; --- Undo handlers ---
.undo_line:
  ; dd, :d and cc: paste the lines back at the recorded line
  JSR undo_restore_line
  JSR set_buf_temp16_one     ; A = 0 (BUF_TEMP16 = 1: one line, one paste)
  ; cc, and a delete of every line, left one empty line there: remove its
  ; newline first.  Its line table entry stays, as the paste point; the
  ; line comes off LINE_COUNT16, which the paste's line check must not
  ; count.  (Typing in cc's line ends the undo, so it is still empty.)
  BIT UNDO_EMPTY_LINE
  BPL .undo_line_paste
  STA BUF_LEN16 + 1
  LDX #1
  STX BUF_LEN16              ; 1 byte
  LDAX16 FILE_LINE16
  JSR mark_adjust_delete
  JSR get_current_line_ptr
  JSR buf_shift_left_16
  DEC16 LINE_COUNT16

.undo_line_paste:
  ; Paste above: reuses existing yank_paste_above_n
  JSR yank_paste_above_n
  BCS .undo_line_fail
  ; Adjust marks for inserted lines
  CP16 YANK_LINES16, BUF_TEMP16
  LDAX16 FILE_LINE16
  JSR mark_adjust_insert
  ; Set flags
  JSR undo_set_done_flags
  LDA YANK_LINES16           ; Actual lines inserted (may differ from net delta)
  STA INSERT_LINE_COUNT
  LDA UNDO_TYPE
  CMP #UNDO_CC
  BNE .undo_line_scroll
  ; cc undo: 1cc has net 0 line change (repaint cursor row only).
  ; Ncc (N>1): displacement may differ from file delta if lines wrap,
  ; so use full repaint for correctness.
  LDA YANK_LINES16
  CMP #2
  BCS .undo_cc_multi
  LDA #RF_LINE
  STA RENDER_FLAG            ; Single line repaint
.undo_line_fail:
  JMP clear_count
.undo_cc_multi:
  ; Ncc undo: compute SCROLL_DELTA = total_screen_rows(pasted) - 1
  ; (subtract 1 for the removed empty line)
  JSR compute_delete_rows_temp16 ; Walks the BUF_TEMP16 = YANK_LINES16 lines
  LDA DELETE_SCREEN_ROWS
  BEQ .undo_cc_full              ; Overflow or 0: fall back to full repaint
  SEC
  SBC #1                         ; Subtract 1 for the removed empty line
  BEQ .undo_cc_full              ; 0 displacement: fall back
  STA SCROLL_DELTA
  LDA #RF_INS_PRESET
  JMP set_render_clear_count     ; Pre-computed insert-scroll
.undo_cc_full:
  LDA #RF_FULL
  JMP set_render_clear_count     ; Fall back to full repaint
.undo_line_scroll:
  LDA #RF_INS
  JMP set_render_clear_count     ; Signal line-insert for scroll optimization

.undo_char:
  ; Re-insert the deleted chars (the yank) at the recorded position
  JSR undo_restore_line_col
  JSR set_buf_temp16_one
  LDA #CP_AT
  JSR do_char_paste          ; Marks and scroll flags for a multi-line yank
  BCS .undo_fail
  JSR undo_restore_col       ; Cursor back to the span start
  JSR undo_set_done_flags
  JMP undo_keep_render_flag  ; Single-line: current line repaint
.undo_fail:
  JMP clear_count

; --- Redo handlers ---
.redo_cc:
  ; cc redo: replace the lines with one empty line again
  JSR undo_restore_lines
  JSR cc_clear_lines
  JMP clear_count

.redo_line:
  ; Restore FILE_LINE16, and the yank's line count: the lines to delete
  JSR undo_restore_lines
  JSR undo_delete_lines_scroll
  JSR undo_set_redone_flags
  JSR clamp_cursor_col
  JMP finish_delete_scroll   ; (the cursor moved up if they reached EOF)

.redo_char:
  ; Restore position
  JSR undo_restore_pos_from
  ; Get yank size for delete count
  JSR yank_get_size          ; BUF_LEN16 = yank size
  BCS .undo_fail
  JSR delete_at_cursor       ; Delete BUF_LEN16 bytes at cursor (sets RF_CHAR_JOIN if multi-line)
  ; Restore cursor
  JSR undo_restore_col
  JSR clamp_cursor_col
  ; Set flags (keep RENDER_FLAG from delete_at_cursor if > 1)
  JMP undo_finish_not_redo

; --- Join undo: replace spaces back to newlines ---
undo_join_undo:
  JSR undo_restore_line
  LDA #'\n'
  JSR undo_join_apply
  JSR mark_adjust_insert

  ; Set flags
  JSR undo_set_done_flags
  ; Repaint cursor line + restored lines (cursor line content also changed)
  LDA UNDO_JOIN_COUNT
  CLC
  ADC #1
  STA INSERT_LINE_COUNT
  LDA #RF_UNJOIN
  STA RENDER_FLAG            ; Line-insert scroll, skip cursor row
  JMP zero_col_clamp_clear

; --- Join redo: replace newlines back to spaces ---
undo_join_redo:
  JSR undo_restore_line

  ; Pre-compute old_total screen rows for displacement-based scroll
  LDA UNDO_JOIN_COUNT
  JSR compute_delete_rows_join

  JSR get_current_line_len
  STA RENDER_FROM_COL16
  STX RENDER_FROM_COL16 + 1

  LDA #' '
  JSR undo_join_apply
  JSR mark_adjust_delete

  ; Set flags
  JSR undo_set_redone_flags
  LDA #RF_JOIN
  STA RENDER_FLAG        ; Line-delete, skip cursor row scroll
  JSR undo_restore_col
  JMP clamp_and_clear_count

; Shared join undo/redo body: write the char in A at each recorded join
; offset on the current line, rebuild lines, then set up the caller's
; mark-adjust call (BUF_TEMP16 = join count, A/X = FILE_LINE16 + 1).
undo_join_apply:
  STA BUF_TEMP16               ; Stash char (BUF_TEMP16 free until epilogue)
  JSR get_current_line_ptr          ; BUF_PTR16 = line start
  CP16 BUF_PTR16, BUF_SRC16    ; BUF_SRC16 = line start (base for offsets)

  LDX #0                       ; X = buffer index
  LDY #0
  LDA UNDO_JOIN_COUNT
  STA NORMAL_TEMP               ; loop counter
.loop:
  ; BUF_PTR16 = line start + recorded offset
  CLC
  LDA UNDO_DATA_BUF,X
  ADC BUF_SRC16
  STA BUF_PTR16
  LDA UNDO_DATA_BUF + 1,X
  ADC BUF_SRC16 + 1
  STA BUF_PTR16 + 1
  INX
  INX
  LDA BUF_TEMP16               ; The stashed char
  STA (BUF_PTR16),Y
  DEC NORMAL_TEMP
  BNE .loop

  JSR buf_rebuild_lines

  ; Mark adjustment: count = UNDO_JOIN_COUNT lines after FILE_LINE16
  LDA UNDO_JOIN_COUNT
  JMP mark_args_next_line

; --- Line paste undo (types 4/5; char paste types 6/7 dispatch directly) ---
undo_paste_undo:
  ; Line paste undo: set FILE_LINE16 to first pasted line
  JSR undo_restore_line
  LDA UNDO_TYPE
  CMP #UNDO_LINE_PASTE_BELOW
  BNE .undo_line_paste
  INC16 FILE_LINE16            ; BELOW: pasted lines start one past saved

.undo_line_paste:
  ; BUF_TEMP16 = YANK_LINES16 * UNDO_PASTE_COUNT16
  JSR undo_compute_paste_lines
  JSR undo_delete_lines_scroll
  ; Restore cursor
  JSR undo_restore_line_col
  JSR clamp_cursor_col
  ; Set flags
  JSR undo_set_done_flags
  JMP finish_delete_scroll

; --- Line paste redo (types 4/5) ---
undo_paste_redo:
  ; Line paste redo: common setup
  JSR undo_restore_line
  CP16 UNDO_PASTE_COUNT16, BUF_TEMP16
  LDA UNDO_TYPE
  CMP #UNDO_LINE_PASTE_ABOVE
  BEQ .redo_line_paste_above
  JSR yank_paste_below_n
  JMP .redo_line_paste_done
.redo_line_paste_above:
  JSR yank_paste_above_n
.redo_line_paste_done:
  BCS undo_paste_fail
  JSR paste_adjust_marks     ; Also sets MODIFIED
  LDA #0
  STA UNDO_IS_REDO
  ; INSERT_LINE_COUNT = total pasted lines (in BUF_TEMP16 from paste_adjust_marks)
  LDA BUF_TEMP16
  STA INSERT_LINE_COUNT
  LDA #RF_INS
  STA RENDER_FLAG
undo_paste_fail:
  JMP clear_count

; Compute BUF_TEMP16 = YANK_LINES16 * UNDO_PASTE_COUNT16 (16-bit, count >= 1)
; Clobbers: A, X, BUF_LEN16, COUNT16, DIV_INPUT16
undo_compute_paste_lines:
  CP16 UNDO_PASTE_COUNT16, BUF_TEMP16
  LDX #YANK_LINES16
  JSR mul_by_count
  STAX16 BUF_TEMP16
  RTS

; Cursor back where a char paste was typed: UNDO_LINE16, and UNDO_COL16
; for P or one column left of it (clamped at column 0) for p
; Returns X = UNDO_TYPE
paste_restore_pos:
  JSR undo_restore_line_col  ; A = UNDO_COL16 high byte
  LDX UNDO_TYPE
  CPX #UNDO_CHAR_PASTE_BELOW
  BNE .done
  ORA UNDO_COL16
  BEQ .done                  ; Column 0 stays
  JMP dec_cursor_col
.done:
  RTS

; --- Char paste undo (handles both BELOW and ABOVE) ---
undo_char_paste_undo:
  ; Position at insertion point and delete pasted content
  JSR undo_restore_pos_from
  CP16 UNDO_PASTE_COUNT16, BUF_TEMP16
  JSR yank_paste_size          ; BUF_LEN16 = total paste size
  BCS undo_paste_fail
  JSR delete_at_cursor         ; Deletes BUF_LEN16 bytes, handles marks
  JSR paste_restore_pos
  JSR clamp_cursor_col
  JSR undo_set_done_flags
  ; Keep RENDER_FLAG from delete_at_cursor if > 1 (multi-line scroll)
  JMP undo_keep_render_flag

; --- Char paste redo (handles both BELOW and ABOVE) ---
undo_char_paste_redo:
  ; The paste runs with no typed-ahead extras (main_loop zeroed BATCH_EXTRA)
  CP16 UNDO_PASTE_COUNT16, BUF_TEMP16
  JSR paste_restore_pos        ; X = UNDO_TYPE
  CPX #UNDO_CHAR_PASTE_ABOVE
  BEQ .redo_cpa
  JSR do_char_paste_below
  JMP undo_finish_not_redo
.redo_cpa:
  JSR do_char_paste_above
  ; Fall through into undo_finish_not_redo

; Common finish: clear the redo flag, then keep RENDER_FLAG from the
; operation if > 1 (multi-line scroll), else single-line repaint
undo_finish_not_redo:
  LDA #0
  STA UNDO_IS_REDO
undo_keep_render_flag:
  LDA RENDER_FLAG
  CMP #RF_DEL
  BCS .done
  LDA #RF_LINE
  STA RENDER_FLAG
.done:
  JMP clear_count

; --- Open-line undo: delete the opened blank line(s) ---
undo_open_undo:
  ; Delete the opened line
  JSR undo_restore_line
  JSR set_buf_temp16_one
  JSR undo_delete_lines_scroll
  ; Restore cursor to the original line (saved in UNDO_COL16), col 0: the
  ; opened line's place (O) or the line above it (o)
  CP16 UNDO_COL16, FILE_LINE16
  LDA #0
  STA_LH16 CURSOR_COL16
  ; Set flags
  JSR undo_set_done_flags
  JMP finish_delete_scroll

; --- Open-line redo: re-insert blank line ---
undo_open_redo:
  ; Insert a blank line at UNDO_LINE16 (on buffer full, nothing moves)
  LDAX16 UNDO_LINE16
  JSR open_line_at
  BCS .redo_open_fail
  ; Set cursor on opened line
  JSR undo_restore_line
  LDA #RF_INS                   ; Insert scroll
  JSR undo_opened_finish
.redo_open_fail:
  JMP clear_count


; --- Indent/unindent undo step (self-morphing) ---
; UNDO_INDENT: spaces were added; undo removes them (remove_spaces_core
; with the recorded width re-records as UNDO_UNINDENT).
; UNDO_UNINDENT: spaces were removed; undo re-inserts the recorded
; per-line counts (insert_spaces_core in data mode re-records as
; UNDO_INDENT).  Cursor returns to the recorded position both ways.
undo_shift_step:
  JSR undo_restore_line_col
  CP16 UNDO_RANGE_LINES16, BUF_TEMP16
  LDA UNDO_WIDTH
  STA BUF_DELTA
  STA SHIFT_UNDO_WIDTH
  LDA UNDO_TYPE
  CMP #UNDO_UNINDENT
  BEQ .reinsert
  JSR remove_spaces_core
  JMP .restore_cursor
.reinsert:
  LDA #$FF
  STA SHIFT_MODE
  JSR insert_spaces_core
.restore_cursor:
  JSR undo_restore_col
  JMP clamp_and_clear_count

; Move the cursor to the recorded span start (the line repaints from
; there) and point BUF_PTR16 at it
undo_span_setup:
  JSR undo_restore_pos_from
  JMP get_cursor_buf_ptr

; Common finishes: set the undone/redone flags, then a single-line
; partial repaint from the span start
undo_span_undone:
  JSR undo_set_done_flags
  JMP undo_span_finish
undo_span_redone:
  JSR undo_set_redone_flags
undo_span_finish:
  LDA #RF_LINE
  JMP set_render_clear_count

; --- Toggle case undo/redo: self-inverse, re-toggle the span ---
undo_tilde_span:
  JSR undo_span_setup
  LDX UNDO_SPAN_LEN
  LDY #0
.loop:
  LDA (BUF_PTR16),Y
  JSR toggle_alpha
  BCS .next                  ; not alpha
  STA (BUF_PTR16),Y
.next:
  INY
  DEX
  BNE .loop
  RTS

undo_tilde_undo:
  JSR undo_tilde_span
  JMP undo_span_undone

undo_tilde_redo:
  JSR undo_tilde_span
  ; Cursor advances past the span as the original ~ did (clamped)
  TYA                        ; Y = span length (UNDO_SPAN_LEN)
  ADDA16 CURSOR_COL16
  JSR clamp_cursor_col
  JMP undo_span_redone

; --- Replace char undo: restore the saved originals ---
undo_replace_undo:
  JSR undo_span_setup
  LDX #0
  LDY #0
.loop:
  LDA UNDO_DATA_BUF,X
  STA (BUF_PTR16),Y
  INY
  INX
  CPX UNDO_SPAN_LEN
  BNE .loop
  JMP undo_span_undone

; --- Replace char redo: re-write the replacement char ---
undo_replace_redo:
  JSR undo_span_setup
  LDA UNDO_REPL_CHAR
  LDX UNDO_SPAN_LEN
  LDY #0
.loop:
  STA (BUF_PTR16),Y
  INY
  DEX
  BNE .loop
  ; Cursor lands on the last replaced char, as the original r did
  DEY
  TYA                        ; A = span length - 1
  ADDA16 CURSOR_COL16
  JMP undo_span_redone

; --- Restore helpers: copy the undo record back into cursor state ---
; Restore FILE_LINE16 and CURSOR_COL16, and repaint the line from the
; recorded column
undo_restore_pos_from:
  CP16 UNDO_COL16, RENDER_FROM_COL16
; Restore FILE_LINE16 and CURSOR_COL16 from the undo record
undo_restore_line_col:
  CP16 UNDO_LINE16, FILE_LINE16
; Restore CURSOR_COL16 from the undo record
undo_restore_col:
  CP16 UNDO_COL16, CURSOR_COL16
  RTS

; Delete BUF_TEMP16 lines at FILE_LINE16 for the $07 line-delete scroll
; (finish_delete_scroll sets it once the cursor is placed)
undo_delete_lines_scroll:
  JSR precompute_delete_scroll
  JMP delete_current_lines

; Pre-compute the line-delete scroll of the BUF_TEMP16 lines at
; FILE_LINE16, before they are deleted: SCROLL_DELTA = their screen rows
; ($FF when over 255 lines or rows), which render_decide uses as is for
; $02 and $07 (clamped to the scroll region), and DELETE_SCREEN_ROWS =
; FILE_LINE16's low byte, the first removed line, for finish_delete_scroll
precompute_delete_scroll:
  JSR compute_delete_rows_temp16
  LDX DELETE_SCREEN_ROWS
  BNE .rows
  DEX                        ; $FF
.rows:
  STX SCROLL_DELTA
  LDA FILE_LINE16
  STA DELETE_SCREEN_ROWS
  RTS

; Set the $07 line-delete scroll once the cursor is placed.  The cursor
; is on the first removed line's place (the next line moved up into its
; rows, so the scroll region starts at the cursor line) or on the line
; above it (p/o undo, a delete that reached EOF), whose rows the region
; skips.  The two differ by one line, so their low bytes differ too.
finish_delete_scroll:
  LDA DELETE_SCREEN_ROWS     ; first removed line (low byte)
  EOR FILE_LINE16
  BNE .above
  ; A = 0: the region starts at the cursor line.  A delete that emptied
  ; the buffer left an empty line there, which did not move up from
  ; below: with one line left, draw every row of the region
  LDX LINE_COUNT16 + 1
  BNE .set
  LDX LINE_COUNT16
  DEX
  BNE .set
  DEX
  STX SCROLL_DELTA           ; $FF
  BNE .set                   ; Always
.above:
  JSR file_line_rows
.set:
  STA DELETE_SCREEN_ROWS
  LDA #RF_DEL_BELOW
  JMP set_render_clear_count

; Restore FILE_LINE16 from the undo record, and BUF_TEMP16 = YANK_LINES16
; (the lines a line delete took, for its redo)
undo_restore_lines:
  CP16 YANK_LINES16, BUF_TEMP16
; Restore FILE_LINE16 from the undo record
undo_restore_line:
  CP16 UNDO_LINE16, FILE_LINE16
  RTS

; Finish a (re)opened blank line: RENDER_FLAG = A, cursor to column 0,
; then mark the operation redone (shared by o/O, cc and their redo)
undo_opened_finish:
  STA RENDER_FLAG
  LDA #0
  STA_LH16 CURSOR_COL16
  ; fall through

; Mark the operation redone: next 'u' undoes, buffer is modified
undo_set_redone_flags:
  LDA #0
  STA UNDO_IS_REDO
  JMP set_modified

; Mark the operation undone: next 'u' redoes, buffer is modified
undo_set_done_flags:
  LDA #$FF
  STA UNDO_IS_REDO
  STA MODIFIED
  RTS
