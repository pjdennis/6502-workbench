; Insert mode handler
;
; In insert mode:
;   - Printable characters ($20-$7E) are inserted at cursor
;   - Enter ($0D) inserts newline
;   - Backspace ($08) deletes char before cursor or joins lines
;   - Delete ($88) deletes char at cursor or joins lines forward
;   - ESC ($1B) returns to normal mode
;
; All editing keys (printable, Enter, BS, DEL) are handled by a single
; unified batch handler (insert_batch) that collects mixed keystrokes
; and consolidates them into: [back N] [insert chars] [fwd N]
; Then executes with a single buffer shift.

  .code

; Handle a keystroke in insert mode
; Key code in A
insert_handle_key:
  STA BUF_TEMP
  ; Route batchable keys directly to insert_batch
  CMP #KEY_ENTER
  BEQ .batch
  CMP #KEY_BS
  BEQ .batch
  CMP #KEY_DEL
  BEQ .batch
  CMP #KEY_TAB
  BEQ .batch
  CMP #' '
  BCC .dispatch
  CMP #$7F
  BCC .batch             ; $20-$7E = printable
.dispatch:
  LDA #<insert_keys
  LDX #>insert_keys
  JSR dispatch_key
  RTS
.batch:
  JMP insert_batch

; --- Dispatch table ---

insert_keys:
  .byte KEY_ESC     .word insert_exit
  .byte KEY_UP      .word insert_counted_move
  .byte KEY_DOWN    .word insert_counted_move
  .byte KEY_LEFT    .word insert_counted_move
  .byte KEY_RIGHT   .word insert_counted_move
  .byte KEY_HOME    .word insert_home
  .byte KEY_END     .word insert_end
  .byte KEY_PGDN    .word insert_page_down
  .byte KEY_PGUP    .word insert_page_up
  .byte $06         .word insert_page_down    ; Ctrl-F
  .byte $02         .word insert_page_up      ; Ctrl-B
  .byte KEY_WORD_FWD  .word insert_counted_move
  .byte KEY_WORD_BACK .word insert_counted_move
  .byte 0           ; End sentinel

; Exit insert mode, return to normal mode
insert_exit:
  LDA INSERT_CHANGED
  BEQ .skip_undo_clear
  JSR undo_clear
.skip_undo_clear:
  LDA #MODE_NORMAL
  STA MODE
  ; Move cursor back one per vi convention (unless at column 0)
  TST16 CURSOR_COL16
  BEQ .done
  JSR dec_cursor_col
.done:
  RTS

; ============================================================================
; Unified batch handler for insert-mode editing
; ============================================================================
;
; Collects a mixed batch of printable/Enter/BS/DEL keys and consolidates
; on-the-fly into canonical form: [back N] [insert BATCH_BUF] [fwd N]
; Then executes with a single buffer shift.
;
; On entry: BUF_TEMP = first key (printable, Enter, BS, or DEL)
;
; Collection phase variables:
;   BUF_TEMP16.lo = back count (BS overflow past batch)
;   BUF_TEMP16.hi = fwd count (DEL)
;   X = BATCH_BUF write index
;   Y = remaining capacity (counts down from BATCH_MAX)
;
; Execution phase variables:
;   BUF_DELTA      = insert_len
;   BUF_TEMP16.lo  = back
;   BUF_TEMP       = fwd_actual (after forward scan)
;   LINE_LEN16.lo  = back_nl
;   LINE_LEN16.hi  = fwd_nl
;   NORMAL_TEMP    = ins_nl (after BATCH_BUF scan)
;   BATCH_EXTRA    = last_nl_pos (after BATCH_BUF scan)
;   BUF_PTR16      = delete_start
;   BUF_SRC16      = forward scan pointer
;   Stack          = cursor_buf_pos (in newline path)
;
insert_batch:
  ; --- Collection phase ---
  LDA #0
  STA BUF_TEMP16           ; back = 0
  STA BUF_TEMP16 + 1       ; fwd = 0
  LDX #0                   ; BATCH_BUF write index
  LDY #BATCH_MAX           ; remaining capacity

  ; Process first key (already in BUF_TEMP)
  LDA BUF_TEMP
  JMP .collect_key

.key_del:
  INC BUF_TEMP16 + 1        ; fwd++
  ; fall through: consume capacity and fetch next key

.dec_cap:
  DEY                       ; DEY sets Z, no CPY needed
  BEQ .collect_done
  JSR key_ready
  CMP #$FF
  BNE .collect_done
  JSR get_key

.collect_key:
  CMP #KEY_ENTER
  BEQ .key_enter
  CMP #KEY_BS
  BEQ .key_bs
  CMP #KEY_DEL
  BEQ .key_del
  CMP #KEY_TAB
  BEQ .key_printable
  ; Check printable ($20-$7E)
  CMP #' '
  BCC .key_other
  CMP #$7F
  BCS .key_other
  ; Printable/tab: store in BATCH_BUF
.key_printable:
  STA BATCH_BUF,X
  INX
  JMP .dec_cap

.key_enter:
  LDA #'\n'
  BNE .key_printable        ; Always taken ($0A != 0)

.key_bs:
  CPX #0
  BEQ .key_bs_overflow
  DEX                       ; Cancel last char in batch
  JMP .dec_cap
.key_bs_overflow:
  INC BUF_TEMP16            ; back++
  JMP .dec_cap

.key_other:
  JSR unget_key

.collect_done:
  ; X = insert_len, BUF_TEMP16.lo = back, BUF_TEMP16.hi = fwd
  STX BUF_DELTA

  ; --- Check for no-op ---
  TXA
  ORA BUF_TEMP16
  ORA BUF_TEMP16 + 1
  BNE .exec_start
  RTS                       ; Nothing to do

.exec_start:
  ; --- Execution phase ---

  ; Step 2: Get cursor buffer position
  JSR get_cursor_buf_ptr    ; BUF_PTR16 = cursor position

  ; Step 3: Clamp back to available bytes before cursor
  ; dist = BUF_PTR16 - TEXT_BUF
  SEC
  LDA BUF_PTR16
  SBC #<TEXT_BUF
  STA BUF_SRC16             ; dist.lo
  LDA BUF_PTR16 + 1
  SBC #>TEXT_BUF
  ; If high byte > 0, back (max 32) fits
  BNE .back_ok
  ; High byte = 0: clamp back to min(back, dist.lo)
  LDA BUF_SRC16
  CMP BUF_TEMP16
  BCS .back_ok
  STA BUF_TEMP16            ; back = dist (clamped)
.back_ok:

  ; Step 4: BUF_PTR16 -= back (delete_start)
  SEC
  LDA BUF_PTR16
  SBC BUF_TEMP16
  STA BUF_PTR16
  LDA BUF_PTR16 + 1
  SBC #0
  STA BUF_PTR16 + 1
  ; BUF_PTR16 = delete_start

  ; Step 5: Count newlines in backward-deleted region [delete_start, delete_start+back)
  LDA #0
  STA LINE_LEN16            ; back_nl = 0
  LDY #0
  LDA BUF_TEMP16            ; back
  BEQ .no_back_scan
.back_scan:
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BNE .back_not_nl
  INC LINE_LEN16
.back_not_nl:
  INY
  CPY BUF_TEMP16
  BNE .back_scan
.no_back_scan:

  ; Pre-compute screen rows for BS join scroll optimization
  LDA LINE_LEN16            ; back_nl
  BEQ .skip_bs_precompute   ; No newlines deleted
  PUSH16 BUF_PTR16          ; Save delete_start
  ; first_line = FILE_LINE16 - back_nl
  LDA FILE_LINE16
  SEC
  SBC LINE_LEN16
  STA RENDER_LINE16
  LDA FILE_LINE16 + 1
  SBC #0
  STA RENDER_LINE16 + 1
  ; count = back_nl + 1
  LDA LINE_LEN16
  CLC
  ADC #1
  JSR compute_delete_screen_rows
  POP16 BUF_PTR16           ; Restore delete_start
.skip_bs_precompute:

  ; Step 6: Scan forward from original cursor, consuming fwd bytes
  ; Original cursor = delete_start + back = BUF_PTR16 + back
  CLC
  LDA BUF_PTR16
  ADC BUF_TEMP16
  STA BUF_SRC16
  LDA BUF_PTR16 + 1
  ADC #0
  STA BUF_SRC16 + 1         ; BUF_SRC16 = original cursor pos

  ; Pre-compute final \n address = BUF_END16 - 1 -> BUF_LEN16 (temp)
  SEC
  LDA BUF_END16
  SBC #1
  STA BUF_LEN16
  LDA BUF_END16 + 1
  SBC #0
  STA BUF_LEN16 + 1

  LDA #0
  STA BUF_TEMP              ; fwd_actual = 0
  STA LINE_LEN16 + 1        ; fwd_nl = 0

.fwd_scan:
  LDA BUF_TEMP16 + 1        ; remaining fwd
  BEQ .fwd_done

  CMP16 BUF_SRC16, BUF_END16
  BCS .fwd_done

  LDY #0
  LDA (BUF_SRC16),Y
  CMP #'\n'
  BNE .fwd_advance

  ; Newline - is it the final one?
  CMP16 BUF_SRC16, BUF_LEN16
  BCS .fwd_done              ; final \n, stop

  INC LINE_LEN16 + 1        ; fwd_nl++

.fwd_advance:
  INC16 BUF_SRC16
  INC BUF_TEMP               ; fwd_actual++
  DEC BUF_TEMP16 + 1         ; remaining fwd--
  JMP .fwd_scan

.fwd_done:
  ; State: BUF_TEMP16.lo=back, BUF_TEMP=fwd_actual, BUF_DELTA=insert_len
  ;        LINE_LEN16.lo=back_nl, LINE_LEN16.hi=fwd_nl
  ;        BUF_PTR16=delete_start

  ; Step 7: Compute net = insert_len - total_delete and shift
  ; total_delete = back + fwd_actual
  LDA BUF_TEMP16             ; back
  CLC
  ADC BUF_TEMP               ; + fwd_actual
  STA BUF_SRC16              ; total_delete (stash in BUF_SRC16.lo)

  ; net = insert_len - total_delete
  LDA BUF_DELTA              ; insert_len
  SEC
  SBC BUF_SRC16              ; - total_delete
  BEQ .no_shift
  BCS .shift_right           ; carry set = no borrow = net > 0

  ; --- net < 0: shift left ---
  ; |net| = total_delete - insert_len
  LDA BUF_SRC16              ; total_delete
  SEC
  SBC BUF_DELTA              ; - insert_len
  STA BUF_LEN16
  LDA #0
  STA BUF_LEN16 + 1
  ; Shift point = delete_start + insert_len
  PUSH16 BUF_PTR16           ; save delete_start
  LDA BUF_DELTA
  CLC
  ADCA16 BUF_PTR16, BUF_PTR16
  JSR buf_shift_left_16
  POP16 BUF_PTR16            ; restore delete_start
  JMP .do_copy

.shift_right:
  ; --- net > 0: A = net ---
  STA BUF_LEN16
  LDA #0
  STA BUF_LEN16 + 1
  ; Shift point = delete_start + total_delete
  PUSH16 BUF_PTR16           ; save delete_start
  LDA BUF_SRC16              ; total_delete
  CLC
  ADCA16 BUF_PTR16, BUF_PTR16
  JSR buf_shift_right_16
  POP16 BUF_PTR16            ; restore delete_start
  BCC .do_copy
  ; Buffer full
  JMP show_buffer_full_msg

.no_shift:
.do_copy:
  ; Steps 8+10: Copy BATCH_BUF to buffer and scan for newlines in one pass
  LDA #0
  STA NORMAL_TEMP            ; ins_nl = 0
  STA BATCH_EXTRA            ; last_nl_pos = 0
  LDA BUF_DELTA
  BEQ .copy_scan_done
  LDY #0
.copy_scan:
  LDA BATCH_BUF,Y
  STA (BUF_PTR16),Y          ; copy
  CMP #'\n'
  BNE .not_nl
  INC NORMAL_TEMP            ; ins_nl++
  TYA
  CLC
  ADC #1
  STA BATCH_EXTRA            ; last_nl_pos = Y + 1
.not_nl:
  INY
  CPY BUF_DELTA
  BNE .copy_scan
.copy_scan_done:

  ; Step 11: Decide path based on newline counts
  LDA LINE_LEN16             ; back_nl
  ORA LINE_LEN16 + 1         ; fwd_nl
  ORA NORMAL_TEMP            ; ins_nl
  BEQ .fast_path
  JMP .newlines_path

  ; ========================================
  ; Fast path: no newlines at all
  ; ========================================
.fast_path:
  ; CURSOR_COL16 = CURSOR_COL16 - back + insert_len
  JSR adjust_cursor_col_ins

  ; RENDER_FROM_COL16 = CURSOR_COL16 - insert_len (first affected col)
  SEC
  SBC16_8 CURSOR_COL16, BUF_DELTA, RENDER_FROM_COL16

  ; Line table adjustment: net = insert_len - (back + fwd_actual)
  LDA BUF_TEMP16             ; back
  CLC
  ADC BUF_TEMP               ; + fwd_actual = total_delete
  STA NORMAL_TEMP            ; stash total_delete (ins_nl is 0 here)
  LDA BUF_DELTA              ; insert_len
  STA SHIFT_WRITE            ; ICH/DCH hint: new cells at RENDER_FROM_COL16
  SEC
  SBC NORMAL_TEMP            ; - total_delete = net
  STA SHIFT_NET              ; ICH/DCH hint: net cell shift
  BEQ .fast_done
  BCS .fast_inc              ; net > 0

  ; net < 0: adjust lines down
  EOR #$FF
  CLC
  ADC #1                     ; |net|
  STA BUF_DELTA
  JSR buf_adjust_lines_dec
  JMP .fast_done

.fast_inc:
  STA BUF_DELTA
  JSR buf_adjust_lines_inc

.fast_done:
  JMP .set_modified

  ; ========================================
  ; Newlines path: rebuild + mark adjust
  ; ========================================
.newlines_path:
  ; Save cursor_buf_pos = BUF_PTR16 + insert_len
  LDA BUF_DELTA
  CLC
  ADC BUF_PTR16
  STA BUF_SRC16
  LDA #0
  ADC BUF_PTR16 + 1
  STA BUF_SRC16 + 1
  PUSH16 BUF_SRC16          ; stack: cursor_buf_pos

  ; Save back for cursor computation in fwd-only case
  LDA BUF_TEMP16
  PHA                        ; stack: back, cursor_buf_pos

  JSR buf_rebuild_lines

  ; --- Mark adjust delete if back_nl + fwd_nl > 0 ---
  LDA LINE_LEN16             ; back_nl
  CLC
  ADC LINE_LEN16 + 1         ; + fwd_nl
  BEQ .no_mark_del

  ; BUF_TEMP16 = count of deleted lines, A/X = first affected line
  JSR ins_mark_adjust_args
  JSR mark_adjust_delete

.no_mark_del:
  ; --- Mark adjust insert if ins_nl > 0 ---
  LDA NORMAL_TEMP            ; ins_nl
  BEQ .no_mark_ins

  JSR ins_mark_adjust_args
  JSR mark_adjust_insert

.no_mark_ins:
  ; --- Update FILE_LINE16 and CURSOR_COL16 ---
  ; Decide sub-case
  LDA NORMAL_TEMP            ; ins_nl
  BNE .case_ins_nl
  LDA LINE_LEN16             ; back_nl
  BNE .jmp_case_back_nl

  ; --- Case: fwd_nl only (no back/insert newlines) ---
  ; FILE_LINE16 unchanged
  ; CURSOR_COL16 = CURSOR_COL16 - back + insert_len
  PLA                        ; back
  STA BUF_TEMP16             ; temp (mark counts fully consumed above)
  JSR adjust_cursor_col_ins
  ; Clean up cursor_buf_pos from stack
  PLA
  PLA
  ; Pre-compute screen rows for fwd_nl join scroll optimization
  JSR set_render_line_to_cursor
  LDA LINE_LEN16 + 1         ; fwd_nl
  CLC
  ADC #1                     ; + cursor line
  JSR compute_delete_screen_rows
  ; Check if pure join (cursor at end of line = joined lines were empty)
  LDA BUF_TEMP16             ; back
  ORA BUF_DELTA              ; insert_len
  BNE .fwd_not_pure
  JSR get_current_line_len    ; A = low, X = high
  CMP CURSOR_COL16
  BNE .fwd_not_pure
  CPX CURSOR_COL16 + 1
  BNE .fwd_not_pure
  LDA #$FF
  STA INSERT_LINE_COUNT       ; Signal: skip cursor row repaint only
.fwd_not_pure:
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  ; Pure fwd_nl join (no back_nl, no ins_nl) -> scroll optimization
  LDA #$06
  STA RENDER_FLAG            ; Line-delete with displacement-based scroll
  JMP .set_modified

.jmp_case_back_nl:
  JMP .case_back_nl

.case_ins_nl:
  ; --- Case: newlines inserted ---
  ; FILE_LINE16 = FILE_LINE16 - back_nl + ins_nl
  SEC
  LDA FILE_LINE16
  SBC LINE_LEN16             ; - back_nl
  STA FILE_LINE16
  LDA FILE_LINE16 + 1
  SBC #0
  STA FILE_LINE16 + 1
  LDA NORMAL_TEMP            ; ins_nl
  CLC
  ADCA16 FILE_LINE16, FILE_LINE16

  ; CURSOR_COL16 = insert_len - last_nl_pos
  SEC
  LDA BUF_DELTA
  SBC BATCH_EXTRA            ; last_nl_pos
  STA CURSOR_COL16
  LDA #0
  STA CURSOR_COL16 + 1

  ; Clean up stack: back + cursor_buf_pos
  PLA
  PLA
  PLA

  ; Check for pure insert (no back_nl, no fwd_nl) -> scroll optimization
  LDA LINE_LEN16             ; back_nl
  ORA LINE_LEN16 + 1         ; fwd_nl
  BNE .set_modified           ; Complex case, fall back to current-line redraw
  ; Signal pure Enter batch (all bytes are newlines, no printable chars)
  ; for start/end-of-line scroll optimization in render
  LDA BUF_DELTA              ; insert_len
  CMP NORMAL_TEMP            ; ins_nl
  BNE .enter_not_pure
  LDA #$01
  STA INSERT_LINE_COUNT      ; Flag: pure Enter batch
.enter_not_pure:
  LDA #$05
  STA RENDER_FLAG            ; Signal line-insert above cursor for scroll optimization
  JMP .set_modified

.case_back_nl:
  ; --- Case: backward newlines deleted, none inserted ---
  ; FILE_LINE16 -= back_nl
  SEC
  LDA FILE_LINE16
  SBC LINE_LEN16
  STA FILE_LINE16
  LDA FILE_LINE16 + 1
  SBC #0
  STA FILE_LINE16 + 1

  ; CURSOR_COL16 = cursor_buf_pos - LINE_TBL[new FILE_LINE16]
  JSR get_current_line_ptr       ; BUF_PTR16 = start of current line

  ; Pop back
  PLA
  STA BUF_TEMP               ; save back for pure-join check
  ; Pop cursor_buf_pos -> BUF_SRC16
  POP16 BUF_SRC16
  ; CURSOR_COL16 = cursor_buf_pos - line_start
  SEC
  SBC16 BUF_SRC16, BUF_PTR16, CURSOR_COL16

  ; Check for pure line join (no fwd_nl) -> scroll optimization
  LDA LINE_LEN16 + 1         ; fwd_nl
  BNE .set_modified           ; Complex case, fall back to current-line redraw
  ; Check if cursor line content unchanged (pure empty-line join):
  ; back == back_nl (all deleted bytes are newlines) AND
  ; (cursor at col 0 OR cursor at end of line)
  LDA BUF_TEMP               ; back
  CMP LINE_LEN16             ; back_nl
  BNE .bs_not_pure
  LDA CURSOR_COL16
  ORA CURSOR_COL16 + 1
  BEQ .bs_pure_at_start      ; Cursor at col 0: empty lines above joined
  ; Check if cursor at end of line (empty line below joined)
  JSR get_current_line_len    ; A = low, X = high
  CMP CURSOR_COL16
  BNE .bs_not_pure
  CPX CURSOR_COL16 + 1
  BNE .bs_not_pure
  ; Cursor moved up: use $FF to keep normal scroll calculation
  LDA #$FF
  STA INSERT_LINE_COUNT
  JMP .bs_not_pure
.bs_pure_at_start:
  LDA BUF_TEMP               ; reload (non-zero)
  STA INSERT_LINE_COUNT       ; Signal pure empty-line join to render
.bs_not_pure:
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  LDA #$06
  STA RENDER_FLAG            ; Line-delete with displacement-based scroll
  JMP .set_modified

.set_modified:
  LDA #$FF
  STA MODIFIED
  STA INSERT_CHANGED
  LDA RENDER_FLAG
  BNE .skip_flag             ; Already set by caller (e.g., scroll optimization)
  LDA #$01
  STA RENDER_FLAG            ; Force at least current-line redraw
.skip_flag:
  RTS

; Arrow key handlers in insert mode
; These implement simple line movement without the normal mode clamping
; that would clamp to len-1 instead of len (one past last char for insert)

; Consolidated insert mode movement handler
; BUF_TEMP = key code (set by insert_handle_key before dispatch)
insert_counted_move:
  ; BUF_TEMP already set by insert_handle_key
  JSR count_pending_key    ; X = pending matching keys
  INX                      ; +1 for current key
  LDA BUF_TEMP
  CMP #KEY_UP
  BEQ .up
  CMP #KEY_DOWN
  BEQ .down
  CMP #KEY_LEFT
  BEQ .left
  CMP #KEY_RIGHT
  BEQ .right
  CMP #KEY_WORD_FWD
  BEQ .word_fwd
  ; Must be KEY_WORD_BACK
  JSR word_backward_x
  JMP clamp_cursor_col_insert
.up:
  JSR move_up_x
  JMP clamp_cursor_col_insert
.down:
  JSR move_down_x
  JMP clamp_cursor_col_insert
.left:
  JMP move_left_x           ; No clamp needed
.right:
  ; Hoist line length calculation (line doesn't change)
  STX BUF_DELTA
  JSR get_line_len_z
  LDX BUF_DELTA
  JMP move_right_x
.word_fwd:
  JSR word_forward_x
  JMP clamp_cursor_col_insert

insert_page_down:
  JSR normal_page_down
  JMP clamp_cursor_col_insert

insert_page_up:
  JSR normal_page_up
  JMP clamp_cursor_col_insert

insert_home:
  TST16 CURSOR_COL16
  BEQ .done            ; Already at column 0
  LDA #0
  STA_LH16 CURSOR_COL16
.done:
  RTS

insert_end:
  JSR ins_len_cmp_col
  BCC .done            ; Cursor past end: leave (clamp handles elsewhere)
  ; At end the copy rewrites CURSOR_COL16 with its own value (no-op)
  CP16 LINE_LEN16, CURSOR_COL16
.done:
  RTS

; Clamp cursor for insert mode (can be one past end of line content)
clamp_cursor_col_insert:
  JSR ins_len_cmp_col
  BCS .ok
  CP16 LINE_LEN16, CURSOR_COL16
.ok:
  RTS

; Get current line length into LINE_LEN16 and compare with CURSOR_COL16
; Output: flags as after CMP16 LINE_LEN16, CURSOR_COL16
ins_len_cmp_col:
  JSR get_current_line_len
  STAX16 LINE_LEN16
  CMP16 LINE_LEN16, CURSOR_COL16
  RTS

; CURSOR_COL16 = CURSOR_COL16 - back (BUF_TEMP16 low) + insert_len (BUF_DELTA)
; Clobbers: A
adjust_cursor_col_ins:
  SEC
  LDA CURSOR_COL16
  SBC BUF_TEMP16
  STA CURSOR_COL16
  LDA CURSOR_COL16 + 1
  SBC #0
  STA CURSOR_COL16 + 1
  LDA BUF_DELTA
  CLC
  ADCA16 CURSOR_COL16, CURSOR_COL16
  RTS

; Compute mark-adjust args for insert_batch's newline path:
; BUF_TEMP16 = A (line count), A/X = FILE_LINE16 + 1 - back_nl (LINE_LEN16)
; Clobbers: A, X, BUF_DST16, BUF_TEMP16
ins_mark_adjust_args:
  JSR set_buf_temp16_a
  ; first_line = FILE_LINE16 - back_nl + 1 (identical mod 2^16 to +1 first)
  SEC
  LDA FILE_LINE16
  SBC LINE_LEN16             ; - back_nl
  STA BUF_DST16
  LDA FILE_LINE16 + 1
  SBC #0
  STA BUF_DST16 + 1
  INC16 BUF_DST16
  LDAX16 BUF_DST16
  RTS
