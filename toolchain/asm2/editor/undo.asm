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
; Saves: type=2, FILE_LINE16, CURSOR_COL16, and the marks (mark_save)
undo_record_char_delete:
  JSR mark_save
  LDA #UNDO_CHAR
  BNE undo_rec_set           ; Always (UNDO_CHAR != 0)

; Record an empty change at the cursor, as vim does for x on an empty
; line: its undo only puts the cursor back there (a shift of no lines,
; which undo_shift_step leaves as it is).  Returns A = 0, Z set
undo_record_empty:
  LDA #0
  STA_LH16 UNDO_RANGE_LINES16
  LDA #UNDO_INDENT
  BNE undo_rec_set           ; Always

; C = 1 if deleting BUF_TEMP16 lines (at most the lines left) from
; FILE_LINE16 empties the buffer: the count reaches LINE_COUNT16 only
; from line 0.  buf_delete_lines then leaves a synthetic empty line.
; Clobbers A
count_is_every_line:
  LDA BUF_TEMP16
  CMP LINE_COUNT16
  LDA BUF_TEMP16 + 1
  SBC LINE_COUNT16 + 1
  RTS

; Record a line-delete for undo
; Call after yank succeeds, before delete, with BUF_TEMP16 = the line
; count (at most the lines left).
; Saves: type=1, FILE_LINE16 and CURSOR_COL16 (undo_line_col),
; UNDO_EMPTY_LINE bit 7 = the delete empties the buffer (undo must
; remove the synthetic empty line)
undo_record_line_delete:
  JSR count_is_every_line
  ROR UNDO_EMPTY_LINE        ; Bit 7 = C
  LDA #UNDO_LINE
undo_rec_set:
  STA UNDO_TYPE
; Record the cursor position (UNDO_LINE16/UNDO_COL16) and whether the
; buffer has lines (UNDO_WAS_EMPTY), and clear the redo flag.  Clobbers A
; (= 0)
undo_record_pos:
  CP16 CURSOR_COL16, UNDO_COL16
  CP16 FILE_LINE16, UNDO_LINE16
  LDA EMPTY_BUF
  STA UNDO_WAS_EMPTY
  LDA #0
  STA UNDO_IS_REDO
  RTS

; Handle 'u' key: one undo or redo step (u alternates between them).
; Batching: consume pending 'u' keys.  An odd total is one step.  An
; even total leaves the text as it was, but as with the keys typed one
; at a time the cursor ends where the second step leaves it, and the
; text counts as changed: run both steps, then draw only the cursor and
; status (and any view move)
undo_handle:
  JSR count_pending_key      ; X = extra u keys in typeahead
  TXA
  LSR                        ; C = odd extras = even total
  BCC undo_step
  JSR undo_step
  JSR undo_step
  LDA UNDO_TYPE
  BEQ .changed               ; An undo with no redo (it ended the record)
  LDA #0
  STA RENDER_FLAG            ; The text is as it was: no content repaint
  STA DELETE_SCREEN_ROWS
.changed:
  RTS

; One undo or redo step, per UNDO_IS_REDO (no-op with nothing to undo)
undo_step:
  LDA UNDO_TYPE
  BEQ .done
  ; u goes to the recorded line: its repaint takes that line's rows
  ; before the change, not those of the line u was typed on
  LDAX16 UNDO_LINE16
  JSR any_line_rows          ; (1 if gone: a delete that reached the end)
  STA PREV_LINE_ROWS
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
  .word undo_shift_step - 1          ; 9 UNDO_INDENT
  .word undo_shift_step - 1          ; 10 UNDO_UNINDENT
  .word undo_tilde_undo - 1          ; 11 UNDO_TILDE
  .word undo_replace_undo - 1        ; 12 UNDO_REPLACE
  .word undo_insert_undo - 1         ; 13 UNDO_INSERT
.redo_table:                         ; Redo handlers
  .word .redo_line - 1               ; 1 UNDO_LINE
  .word .redo_char - 1               ; 2 UNDO_CHAR
  .word .redo_cc - 1                 ; 3 UNDO_CC
  .word undo_paste_redo - 1          ; 4 UNDO_LINE_PASTE_BELOW
  .word undo_paste_redo - 1          ; 5 UNDO_LINE_PASTE_ABOVE
  .word undo_char_paste_redo - 1     ; 6 UNDO_CHAR_PASTE_BELOW
  .word undo_char_paste_redo - 1     ; 7 UNDO_CHAR_PASTE_ABOVE
  .word undo_join_redo - 1           ; 8 UNDO_JOIN
  .word undo_shift_step - 1          ; 9 UNDO_INDENT
  .word undo_shift_step - 1          ; 10 UNDO_UNINDENT
  .word undo_tilde_redo - 1          ; 11 UNDO_TILDE
  .word undo_replace_redo - 1        ; 12 UNDO_REPLACE
  .word undo_insert_redo - 1         ; 13 UNDO_INSERT

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
  JSR undo_line_col
  ; Adjust marks for inserted lines
  CP16 YANK_LINES16, BUF_TEMP16
  LDAX16 FILE_LINE16
  JSR mark_adjust_insert
  ; Set flags
  JSR undo_set_done_flags
  LDA UNDO_TYPE
  CMP #UNDO_CC
  BNE .undo_line_scroll
  JSR mark_restore           ; cc: the marks as they were (vim)
.undo_line_scroll:
  ; The lines went in at the cursor line (RF_INS), or in place of the
  ; empty line left there (RF_SPLIT)
  LDA UNDO_EMPTY_LINE
  ASL                        ; C = the empty line went
  LDA #RF_INS
  ADC #0
  JMP set_render_clear_count
.undo_line_fail:
  JMP clear_count

.undo_char:
  ; Re-insert the deleted chars (the yank) at the recorded position
  JSR undo_restore_line_col
  JSR set_buf_temp16_one
  LDA #CP_AT
  JSR do_char_paste          ; Marks and scroll flags for a multi-line yank
  BCS .undo_fail
  JSR mark_restore           ; The marks as they were (vim)
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
  JSR undo_line_col          ; (clamped to the line that moves up)
  JSR undo_delete_lines_scroll  ; C = 1: they reached EOF
  BCC .redo_line_col
  JSR first_nonblank         ; On the line above: its first non-blank
.redo_line_col:
  JSR undo_set_redone_flags
  JSR clamp_cursor_col
  JMP finish_delete_scroll   ; (the cursor moved up if they reached EOF)

.redo_char:
  ; Restore position
  JSR undo_restore_line_col
  ; Get yank size for delete count
  JSR yank_get_size          ; BUF_LEN16 = yank size
  BCS .undo_fail
  JSR delete_at_cursor       ; Delete BUF_LEN16 bytes at cursor (sets RF_JOIN if multi-line)
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
  ; The cursor line split from the first join point on
  JSR set_render_from_line_end
  LDA #RF_SPLIT
  STA RENDER_FLAG
  CP16 UNDO_JOIN_COL16, CURSOR_COL16 ; Where the J was typed
  JMP clamp_and_clear_count

; --- Join redo: replace newlines back to spaces ---
undo_join_redo:
  JSR undo_restore_line

  ; Pre-compute old_total screen rows for displacement-based scroll
  LDA UNDO_JOIN_COUNT
  JSR compute_delete_rows_join

  JSR set_render_from_line_end

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
  JSR ptr_to_src               ; BUF_SRC16 = line start (base for offsets)

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
; for P or one column left of it (clamped at column 0) for p; BUF_TEMP16
; = the copies it pasted
; Returns X = UNDO_TYPE
paste_restore_pos:
  JSR undo_restore_count     ; A = UNDO_COL16 high byte
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
  JSR undo_restore_count
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
  CMP #RF_LINE + 1
  BCS .done
  LDA #RF_LINE
  STA RENDER_FLAG
.done:
  JMP clear_count

; --- Insert undo: delete the text the segment typed ---
; The text is kept in UNDO_DATA_BUF for the redo when it fits (at most
; 255 bytes); else the undo ends the record, and u after it does nothing.
; The cursor goes back where the typing began (clamped), as vim's u and
; Ctrl-R put it.  A segment of o or O is whole lines (the opened line's
; break ends it): they go and come back as lines, drawn as the undo and
; redo of a line paste, and u returns to where o or O was typed
undo_insert_undo:
  JSR insert_undo_setup      ; Y = the length's low byte, Z = it fits
  BEQ .save
  JSR undo_clear             ; Too long: no redo (Z = 1)
  BEQ .delete                ; Always
.save:
  DEY
  LDA (BUF_PTR16),Y
  STA UNDO_DATA_BUF,Y
  TYA
  BNE .save
.delete:
  LDA UNDO_INS_OPEN
  BNE .lines
  JSR delete_at_cursor       ; (marks, and the scroll of joined lines)
  JSR clamp_cursor_col
  JMP undo_span_undone
.lines:
  JSR count_newlines         ; BUF_TEMP16 = the lines
  JSR undo_delete_lines_scroll
  ; The line o or O was typed on: for o the one above
  LDA UNDO_INS_OPEN
  LSR                        ; C = 1: O
  LDA UNDO_LINE16
  SBC #0
  STA FILE_LINE16
  LDA UNDO_LINE16 + 1
  SBC #0
  STA FILE_LINE16 + 1
  JSR insert_ret_col
  JSR undo_set_done_flags
  JMP finish_delete_scroll

; --- Insert redo: put the text back from UNDO_DATA_BUF ---
; (It fits: its undo made the room, and nothing has changed since)
undo_insert_redo:
  JSR insert_undo_setup
  JSR buf_shift_right_16
  LDX #0                     ; The line breaks
  LDY BUF_LEN16
  BEQ .one_line              ; An empty change
.copy:
  DEY
  LDA UNDO_DATA_BUF,Y
  STA (BUF_PTR16),Y
  CMP #'\n'
  BNE .next
  INX
.next:
  TYA
  BNE .copy
  TXA
  BEQ .one_line
  PHA
  JSR buf_rebuild_lines
  PLA
  LDY UNDO_INS_OPEN
  BNE .lines
  ; Line breaks: a split of the cursor line, as the undo of a char delete
  ; over them
  JSR mark_args_next_line
  JSR mark_adjust_insert     ; The marks below move down
  LDA #RF_SPLIT
  BNE .flag                  ; Always
.lines:
  ; o or O: the lines go in at the cursor line, as o and O draw them
  ; (the cursor stays on the first, where O was typed; vim returns to the
  ; line o was typed on)
  JSR set_buf_temp16_a
  LDAX16 FILE_LINE16
  JSR mark_adjust_insert     ; The marks from there move down
  JSR insert_ret_col
  LDA #RF_INS
.flag:
  STA RENDER_FLAG
  BNE .done                  ; Always
.one_line:
  JSR buf_adjust_lines_len   ; The lines below move by the length
.done:
  JSR clamp_cursor_col
  JMP undo_span_redone

; The cursor to the insert segment's start (the line repaints from
; there), BUF_PTR16 = its address, BUF_LEN16 = the text's length (and the
; line break of o or O after it), Y = its low byte; Z = 1 if it fits
; UNDO_DATA_BUF
insert_undo_setup:
  JSR undo_span_setup
  LDA UNDO_INS_OPEN
  CMP #1                     ; C = 1: o or O
  LDA UNDO_INS_LEN16
  ADC #0
  STA BUF_LEN16
  TAY
  LDA UNDO_INS_LEN16 + 1
  ADC #0
  STA BUF_LEN16 + 1
  RTS

; The column u returns to after an insert of o or O (clamped)
insert_ret_col:
  CP16 UNDO_RET_COL16, CURSOR_COL16
  JMP clamp_cursor_col


; --- Indent/unindent undo step (self-morphing) ---
; UNDO_INDENT: spaces were added; undo removes them (remove_spaces_core
; with the one-step width INDENT_WIDTH re-records as UNDO_UNINDENT).
; UNDO_UNINDENT: spaces were removed; undo re-inserts the recorded
; per-line counts (insert_spaces_core in data mode re-records as
; UNDO_INDENT).  Cursor returns to the recorded position both ways.
undo_shift_step:
  JSR undo_restore_count       ; (BUF_TEMP16 = UNDO_RANGE_LINES16)
  JSR shift_unit_setup
  LDA UNDO_TYPE
  CMP #UNDO_UNINDENT
  BEQ .reinsert
  JSR remove_spaces_core
  JMP clamp_and_clear_count
.reinsert:
  DEC SHIFT_MODE               ; $FF: the recorded widths
  JSR insert_spaces_core
  JMP clamp_and_clear_count

; Move the cursor to the recorded span start (the line repaints from
; there) and point BUF_PTR16 at it
undo_span_setup:
  CP16 UNDO_COL16, RENDER_FROM_COL16
  JSR undo_restore_line_col
  JMP get_cursor_buf_ptr

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
; For r<Enter> (UNDO_REPL_CHAR = KEY_ENTER) the line break first takes
; back the room of the chars replace_split removed, so the originals
; replace it too and join the next line back (RF_JOIN render, as J)
undo_replace_undo:
  JSR undo_span_setup
  LDA UNDO_REPL_CHAR
  CMP #KEY_ENTER
  PHP                        ; Z = r<Enter>
  BNE .restore
  LDA #1
  JSR compute_delete_rows_join  ; The two lines' rows
  JSR get_cursor_buf_ptr
  JSR replace_extra_len
  BEQ .restore
  JSR buf_shift_right_16     ; (Room: the r<Enter> made it)
.restore:
  LDX #0
  LDY #0
.loop:
  LDA UNDO_DATA_BUF,X
  STA (BUF_PTR16),Y
  INY
  INX
  CPX UNDO_SPAN_LEN
  BNE .loop
  PLP
  BNE undo_span_undone
  JSR buf_rebuild_lines
  LDA #1
  JSR mark_args_next_line
  JSR mark_adjust_delete     ; The next line's marks go, those below move up
  LDA #RF_JOIN
  STA RENDER_FLAG
  ; fall through

; Common finishes of ~ and r: set the undone/redone flags, then a
; single-line partial repaint from the span start (unless the handler
; set a flag of its own)
undo_span_undone:
  JSR undo_set_done_flags
  JMP undo_keep_render_flag

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
  CMP #KEY_ENTER
  BNE .not_split
  JMP replace_split          ; r<Enter>: split the line again
.not_split:
  ; Cursor lands on the last replaced char, as the original r did
  DEY
  TYA                        ; A = span length - 1
  ADDA16 CURSOR_COL16
  ; fall through
undo_span_redone:
  JSR undo_set_redone_flags
  JMP undo_keep_render_flag

; --- Restore helpers: copy the undo record back into cursor state ---
; BUF_TEMP16 = the record's count (UNDO_PASTE_COUNT16: the copies a char
; paste made, or UNDO_RANGE_LINES16, the lines of a >> or <<), then:
undo_restore_count:
  CP16 UNDO_PASTE_COUNT16, BUF_TEMP16
; Restore FILE_LINE16 and CURSOR_COL16 from the undo record
undo_restore_line_col:
  CP16 UNDO_LINE16, FILE_LINE16
; Restore CURSOR_COL16 from the undo record
undo_restore_col:
  CP16 UNDO_COL16, CURSOR_COL16
  RTS

; The column u of a line delete (dd, :d, cc) and its redo go to, as in
; vim: the recorded one, where the delete was typed, but for one line
; not right of the first non-blank, where vim's operator starts (a
; typed-ahead dd and :d recorded it past the line end: the first non-
; blank).  The cursor is on the line put back, or to be deleted again.
; Clobbers A, X, Y, BUF_PTR16
undo_line_col:
  JSR undo_restore_col
  LDA YANK_LINES16
  EOR #1
  ORA YANK_LINES16 + 1
  BNE .done                  ; Two lines or more
  JMP nonblank_left
.done:
  RTS

; Delete BUF_TEMP16 lines at FILE_LINE16 for the RF_DEL line-delete scroll
; (finish_delete_scroll sets it once the cursor is placed).  Returns C = 1
; if they reached EOF: the cursor moved up to the line above
undo_delete_lines_scroll:
  JSR precompute_delete_scroll
  JMP delete_current_lines

; Pre-compute the line-delete scroll of the BUF_TEMP16 lines at
; FILE_LINE16, before they are deleted: SCROLL_DELTA = their screen rows
; ($FF when over 255 lines or rows, or when they are every line: the
; empty line left behind does not move up from below, so the whole
; region is drawn), which render_decide uses as is for RF_DEL (clamped
; to the scroll region), and DELETE_SCREEN_ROWS = FILE_LINE16's low
; byte, the first removed line, for finish_delete_scroll
precompute_delete_scroll:
  LDX #$FF
  JSR count_is_every_line
  BCS .rows
  JSR compute_delete_rows_temp16
  LDX DELETE_SCREEN_ROWS
  BNE .rows
  DEX                        ; $FF
.rows:
  STX SCROLL_DELTA
  LDA FILE_LINE16
  STA DELETE_SCREEN_ROWS
  RTS

; Set the RF_DEL line-delete scroll once the cursor is placed.  The cursor
; is on the first removed line's place (the next line moved up into its
; rows, so the scroll region starts at the cursor line) or on the line
; above it (p/o undo, a delete that reached EOF), whose rows the region
; skips.  The two differ by one line, so their low bytes differ too.
finish_delete_scroll:
  LDA DELETE_SCREEN_ROWS     ; first removed line (low byte)
  EOR FILE_LINE16
  BEQ .set                   ; A = 0: the region starts at the cursor line
  JSR file_line_rows
.set:
  STA DELETE_SCREEN_ROWS
  LDA #RF_DEL
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

; Mark the operation undone: next 'u' redoes, buffer is modified, and it
; has lines unless it had none before the change (vim)
undo_set_done_flags:
  LDA UNDO_WAS_EMPTY
  STA EMPTY_BUF
  LDA #$FF
  STA UNDO_IS_REDO
  STA MODIFIED
  RTS
