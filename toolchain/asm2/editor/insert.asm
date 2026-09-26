; Insert mode handler
;
; In insert mode:
;   - Printable characters ($20-$7E) and Tab are inserted at the cursor
;   - Enter ($0D) inserts a newline
;   - Backspace ($08) deletes the char before the cursor or joins lines
;   - Delete ($88) deletes the char at the cursor or joins lines forward
;   - Other keys (ESC, arrows, Home/End, PgUp/PgDn, Ctrl-F/B, Ctrl-arrows)
;     are dispatched through insert_keys; ESC returns to normal mode
;
; insert_handle_key collects a batch of mixed editing keys (up to
; BATCH_MAX) and consolidates it on the fly into canonical form
;   [back N] [insert BATCH_BUF] [fwd N]
; which it then executes with a single buffer shift.

  .code

; --- Dispatch table ---

insert_keys:
  .byte KEY_ESC     .word insert_exit
  .byte KEY_UP      .word insert_up
  .byte KEY_DOWN    .word insert_down
  .byte KEY_LEFT    .word insert_left
  .byte KEY_RIGHT   .word insert_right
  .byte KEY_HOME    .word normal_line_start   ; Col 0 (no count in insert mode)
  .byte KEY_END     .word insert_end
  .byte KEY_PGDN    .word normal_page_down    ; These land on col 0, so need
  .byte KEY_PGUP    .word normal_page_up      ; no insert-mode clamp
  .byte $06         .word normal_page_down    ; Ctrl-F
  .byte $02         .word normal_page_up      ; Ctrl-B
  .byte KEY_WORD_FWD  .word insert_word_fwd
  .byte KEY_WORD_BACK .word insert_word_back
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
  LDX #1
  JMP move_left_x

; ============================================================================
; Batch handler for insert-mode editing keys
; ============================================================================
;
; On entry: A = the key.  A first key that is not an editing key is
; dispatched through insert_keys instead.
;
; Collection phase variables:
;   BUF_TEMP16.lo = back count (BS overflow past batch)
;   BUF_TEMP16.hi = fwd count (DEL)
;   X = BATCH_BUF write index
;   Y = remaining capacity (counts down from BATCH_MAX)
;
; Execution phase variables:
;   BUF_DELTA      = insert_len
;   BUF_TEMP16.lo  = back (clamped to the bytes before the cursor)
;   BUF_TEMP       = fwd_actual (the forward scan never takes the buffer's
;                    final '\n'); back again in the newline path, where the
;                    mark adjustment clobbers BUF_TEMP16
;   LINE_LEN16.lo  = back_nl
;   LINE_LEN16.hi  = fwd_nl
;   NORMAL_TEMP    = ins_nl (after BATCH_BUF scan)
;   BUF_PTR16      = delete_start (cursor - back)
;   BUF_SRC16      = forward scan pointer
;   SHIFT_NET      = net = insert_len - back - fwd_actual
;   BUF_LEN16      = cursor_buf_pos = delete_start + insert_len (in the
;                    newline path)
;
insert_handle_key:
  STA BUF_TEMP              ; key code (for dispatch_key / insert_move_count)
  ; --- Collection phase ---
  LDX #0                    ; BATCH_BUF write index
  STX BUF_TEMP16            ; back = 0
  STX BUF_TEMP16 + 1        ; fwd = 0
  LDY #BATCH_MAX            ; remaining capacity
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
  BNE .dec_cap              ; Always taken (X <= BATCH_MAX)

.key_enter:
  LDA #'\n'
  BNE .key_printable        ; Always taken ($0A != 0)

.key_bs:
  TXA
  BEQ .key_bs_overflow
  DEX                       ; Cancel last char in batch
  BPL .dec_cap              ; Always taken (X < BATCH_MAX)
.key_bs_overflow:
  INC BUF_TEMP16            ; back++
  BNE .dec_cap              ; Always taken (back <= BATCH_MAX)

.key_del:
  INC BUF_TEMP16 + 1        ; fwd++
  ; fall through: consume capacity and fetch next key

.dec_cap:
  DEY                       ; DEY sets Z, no CPY needed
  BEQ .collect_done
  JSR key_peek              ; A = next key
  BCC .collect_done
  INC HAS_KEY_DECODED       ; Consume it ($FF -> $00)
  BEQ .collect_key          ; Always taken (INC gave $00)

.key_other:
  CPY #BATCH_MAX
  BNE .end_batch
  ; The first key is not an editing key: dispatch it (BUF_TEMP = key)
  LDA #<insert_keys
  LDX #>insert_keys
  JMP dispatch_key
.end_batch:
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

  ; Step 3: Clamp back to available bytes before cursor.  TEXT_BUF is
  ; page-aligned, so only a cursor in its first page can be fewer than
  ; back (max 32) bytes from the start, and then dist = BUF_PTR16.lo
  LDA BUF_PTR16 + 1
  CMP #>TEXT_BUF
  BNE .back_ok
  LDA BUF_PTR16
  CMP BUF_TEMP16
  BCS .back_ok
  STA BUF_TEMP16            ; back = dist (clamped)
.back_ok:
  ; The forward scan (step 6) starts at the cursor
  CP16 BUF_PTR16, BUF_SRC16

  ; Step 4: BUF_PTR16 -= back (delete_start)
  SEC
  SBC16_8 BUF_PTR16, BUF_TEMP16, BUF_PTR16

  ; Step 5: Count newlines in backward-deleted region [delete_start, delete_start+back)
  LDY #0
  STY LINE_LEN16            ; back_nl = 0
  LDY BUF_TEMP16            ; back
.back_scan:
  DEY
  BMI .no_back_scan         ; back <= BATCH_MAX < 128
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BNE .back_scan
  INC LINE_LEN16
  BNE .back_scan            ; Always taken (back_nl <= BATCH_MAX)
.no_back_scan:

  ; Step 6: Scan forward from the cursor (BUF_SRC16), consuming fwd bytes.
  ; The buffer always ends in '\n', where the scan stops, so it needs no
  ; BUF_END16 test of its own
  LDA #0
  STA BUF_TEMP              ; fwd_actual = 0
  STA LINE_LEN16 + 1        ; fwd_nl = 0

.fwd_scan:
  LDA BUF_TEMP16 + 1        ; remaining fwd
  BEQ .fwd_done

  LDY #0
  LDA (BUF_SRC16),Y
  INC16 BUF_SRC16           ; (preserves A)
  CMP #'\n'
  BNE .fwd_advance

  ; Newline - is it the final one (the next byte is BUF_END16)?
  CMP16 BUF_SRC16, BUF_END16
  BCS .fwd_done              ; final \n, stop

  INC LINE_LEN16 + 1        ; fwd_nl++

.fwd_advance:
  INC BUF_TEMP               ; fwd_actual++
  DEC BUF_TEMP16 + 1         ; remaining fwd--
  BPL .fwd_scan              ; Always taken (remaining fwd >= 0)

.fwd_done:
  ; State: BUF_TEMP16.lo=back, BUF_TEMP=fwd_actual, BUF_DELTA=insert_len
  ;        LINE_LEN16.lo=back_nl, LINE_LEN16.hi=fwd_nl
  ;        BUF_PTR16=delete_start

  ; A join's scroll: the screen rows of the lines it joins, before the
  ; edit (the cursor line, back_nl lines above it and fwd_nl below)
  LDA LINE_LEN16             ; back_nl
  CLC
  ADC LINE_LEN16 + 1         ; + fwd_nl
  BEQ .no_join_rows
  TAX
  PUSH16 BUF_PTR16           ; save delete_start
  SEC
  SBC16_8 FILE_LINE16, LINE_LEN16, RENDER_LINE16  ; the first of them
  INX
  TXA                        ; count = back_nl + fwd_nl + 1
  JSR compute_delete_screen_rows
  POP16 BUF_PTR16            ; restore delete_start
.no_join_rows:

  ; Step 7: Count the newlines in BATCH_BUF
  LDY #0
  STY NORMAL_TEMP            ; ins_nl = 0
.nl_scan:
  CPY BUF_DELTA
  BEQ .nl_scanned
  LDA BATCH_BUF,Y
  INY
  CMP #'\n'
  BNE .nl_scan
  INC NORMAL_TEMP            ; ins_nl++
  BNE .nl_scan               ; Always taken (ins_nl > 0)
.nl_scanned:
  ; Refuse the batch before changing anything if its net new lines
  ; (ins_nl - back_nl - fwd_nl) do not fit the line table
  LDA NORMAL_TEMP            ; ins_nl
  SEC
  SBC LINE_LEN16             ; - back_nl
  SBC LINE_LEN16 + 1         ; - fwd_nl (1 more after a borrow: still < 0)
  BMI .lines_fit             ; Net fewer lines
  LDX #0
  JSR check_line_room
  BCS .batch_full
.lines_fit:

  ; Step 8: net = insert_len - total_delete (total_delete = back + fwd_actual)
  LDA BUF_TEMP16             ; back
  CLC
  ADC BUF_TEMP               ; + fwd_actual
  STA BUF_SRC16              ; total_delete (stash in BUF_SRC16.lo)
  LDA BUF_DELTA              ; insert_len
  SEC
  SBC BUF_SRC16              ; - total_delete
  STA SHIFT_NET              ; net (also the fast path's ICH/DCH hint)
  BEQ .do_copy
  ; Shift the tail by |net| at delete_start + min(insert_len, total_delete)
  LDX BUF_SRC16              ; net > 0: grow after the deleted bytes
  BCS .have_len              ; carry set = no borrow = net > 0
  LDX BUF_DELTA              ; net < 0: shrink after the inserted bytes
  EOR #$FF
  ADC #1                     ; C = 0 here: A = |net|
.have_len:
  STA BUF_LEN16
  LDA #0
  STA BUF_LEN16 + 1
  PUSH16 BUF_PTR16           ; save delete_start
  TXA
  JSR ptr_add_a
  BIT SHIFT_NET
  BMI .shrink                ; |net| <= BATCH_MAX < 128
  JSR buf_shift_right_16     ; carry set = buffer full
  JMP .shifted
.shrink:
  JSR buf_shift_left_16
  CLC
.shifted:
  POP16 BUF_PTR16            ; restore delete_start (carry kept)
  BCC .do_copy
.batch_full:
  JMP show_buffer_full_msg

.do_copy:
  ; Step 9: Copy BATCH_BUF to the buffer, last byte first
  LDY BUF_DELTA
  BEQ .copy_done
.copy_loop:
  LDA BATCH_BUF - $01,Y
  DEY
  STA (BUF_PTR16),Y
  BNE .copy_loop             ; Z from the DEY
.copy_done:

  ; Step 10: Decide path based on newline counts
  LDA LINE_LEN16             ; back_nl
  ORA LINE_LEN16 + 1         ; fwd_nl
  BNE .newlines_path
  ; No newline deleted: the batch changed its one line from
  ; RENDER_FROM_COL16 = CURSOR_COL16 - back (first affected col)
  LDA BUF_TEMP16             ; back
  JSR set_render_from_before_cursor
  LDA NORMAL_TEMP            ; ins_nl
  BNE .newlines_path         ; ... and split it

  ; ========================================
  ; Fast path: no newlines at all
  ; ========================================
  ; CURSOR_COL16 = RENDER_FROM_COL16 + insert_len
  LDA BUF_DELTA              ; insert_len
  STA SHIFT_WRITE            ; ICH/DCH hint: new cells at RENDER_FROM_COL16
  CLC
  ADCA16 RENDER_FROM_COL16, CURSOR_COL16

  ; Line table adjustment: add the signed net (SHIFT_NET) to the pointers
  ; of the following lines
  LDX #0
  LDA SHIFT_NET
  BEQ .set_modified_line
  BPL .net_positive
  DEX                        ; sign-extend
.net_positive:
  STA BUF_SRC16
  STX BUF_SRC16 + 1
  JSR buf_adjust_lines_apply
.set_modified_line:
  LDA #RF_LINE                   ; Current-line redraw
.set_render_flag:
  STA RENDER_FLAG            ; (0 on entry: main_loop clears it)
  LDA #$FF
  STA MODIFIED
  STA INSERT_CHANGED
  RTS

  ; ========================================
  ; Newlines path: rebuild + mark adjust
  ; ========================================
.newlines_path:
  ; The mark adjustment clobbers BUF_TEMP16: keep back in BUF_TEMP
  ; (fwd_actual is not needed any more)
  LDA BUF_TEMP16
  STA BUF_TEMP
  ; BUF_LEN16 = cursor_buf_pos = delete_start + insert_len (survives the
  ; rebuild and the mark adjustment)
  LDA BUF_DELTA
  CLC
  ADCA16 BUF_PTR16, BUF_LEN16

  JSR buf_rebuild_lines

  ; FILE_LINE16 = first merged line (the line holding delete_start)
  SEC
  SBC16_8 FILE_LINE16, LINE_LEN16, FILE_LINE16

  ; --- Mark adjust delete if back_nl + fwd_nl > 0 ---
  LDA LINE_LEN16             ; back_nl
  CLC
  ADC LINE_LEN16 + 1         ; + fwd_nl
  BEQ .no_mark_del
  ; BUF_TEMP16 = count of deleted lines, A/X = first affected line
  JSR mark_args_next_line
  JSR mark_adjust_delete
.no_mark_del:
  ; --- Mark adjust insert if ins_nl > 0 ---
  LDA NORMAL_TEMP            ; ins_nl
  BEQ .no_mark_ins
  JSR mark_args_next_line
  JSR mark_adjust_insert
.no_mark_ins:

  ; --- Cursor: FILE_LINE16 += ins_nl, CURSOR_COL16 = cursor_buf_pos -
  ; start of that line (the line after the last inserted newline, else
  ; the first merged line) ---
  LDA NORMAL_TEMP            ; ins_nl
  ADDA16 FILE_LINE16
  JSR get_current_line_ptr
  SEC
  SBC16 BUF_LEN16, BUF_PTR16, CURSOR_COL16

  ; --- Render hints ---
  LDA NORMAL_TEMP            ; ins_nl
  BEQ .joined
  ; Newlines inserted.  Also merged: complex case, current-line redraw
  LDA LINE_LEN16             ; back_nl
  ORA LINE_LEN16 + 1         ; fwd_nl
.complex:
  BNE .set_modified_line
  ; A pure Enter batch (all bytes are newlines) at the end of the line
  ; (the cursor line is empty: INSERT_LINE_COUNT = 1) or at its start
  ; (the first changed column is 0: $FF) is drawn by the scroll alone
  LDA BUF_DELTA              ; insert_len
  CMP NORMAL_TEMP            ; ins_nl
  BNE .enter_flag
  LDY #0
  LDA (BUF_PTR16),Y          ; the char at the cursor (column 0)
  LDX #1
  CMP #'\n'
  BEQ .enter_kind
  LDA RENDER_FROM_COL16
  ORA RENDER_FROM_COL16 + 1
  BNE .enter_flag
  DEX
  DEX                        ; $FF
.enter_kind:
  STX INSERT_LINE_COUNT
.enter_flag:
  LDA #RF_ENTER              ; Line-insert above cursor scroll
  BNE .set_flag              ; Always taken

  ; Lines merged, none inserted: line-delete scroll ($06)
.joined:
  LDA LINE_LEN16             ; back_nl
  BEQ .fwd_join
  ; --- Backward newlines deleted.  Forward ones too: complex case,
  ; current-line redraw ---
  LDA LINE_LEN16 + 1         ; fwd_nl
  BNE .complex               ; (Z = 0: on to .set_modified_line)
  ; Check if cursor line content unchanged (pure empty-line join):
  ; back == back_nl (all deleted bytes are newlines) AND
  ; (cursor at col 0 OR cursor at end of line)
  LDA BUF_TEMP               ; back
  CMP LINE_LEN16             ; back_nl
  BNE .join_flag
  LDA CURSOR_COL16
  ORA CURSOR_COL16 + 1
  BNE .join_at_eol
  ; Cursor at col 0: empty lines above joined; signal with back (non-zero)
  LDA BUF_TEMP
  BNE .join_signal           ; Always taken

  ; --- Forward newlines deleted only ---
.fwd_join:
  ; Pure join (cursor at end of line = joined lines were empty)?
  LDA BUF_TEMP               ; back
  ORA BUF_DELTA              ; insert_len
  BNE .join_flag
.join_at_eol:
  JSR get_current_line_len   ; A = low, X = high
  CMP CURSOR_COL16
  BNE .join_flag
  CPX CURSOR_COL16 + 1
  BNE .join_flag
  LDA #$FF                   ; Signal: skip cursor row repaint only
.join_signal:
  STA INSERT_LINE_COUNT
.join_flag:
  ; The joined line changed from where the batch began, before the text
  ; it typed
  LDA BUF_DELTA              ; insert_len
  JSR set_render_from_before_cursor
  LDA #RF_JOIN               ; Line-delete with displacement-based scroll
.set_flag:
  JMP .set_render_flag

; Arrow key and word motion handlers in insert mode, counted with pending
; repeats of the same key.  In insert mode the cursor may sit one past the
; last char (col = len), so they clamp to len, not len - 1 as normal mode
; does.  Word motions already stay within 0..len, so need no clamp.
insert_word_fwd:
  JSR insert_move_count
  JMP word_forward_x

insert_word_back:
  JSR insert_move_count
  JMP word_backward_x

insert_left:
  JSR insert_move_count
  JMP move_left_x

insert_right:
  JSR get_line_len_z         ; LINE_LEN16 = max col (line doesn't change)
  JSR insert_move_count
  JMP move_right_x

insert_up:
  JSR insert_move_count
  JSR move_up_x
  JMP clamp_cursor_col_insert

insert_down:
  JSR insert_move_count
  JSR move_down_x
  ; fall through

; Clamp cursor for insert mode (can be one past end of line content)
clamp_cursor_col_insert:
  JSR get_current_line_len   ; A/X = len
  CPX CURSOR_COL16 + 1
  BCC set_cursor_col_ax      ; len < col
  BNE .ok
  CMP CURSOR_COL16
  BCC set_cursor_col_ax      ; len < col
.ok:
  RTS

insert_end:
  JSR get_current_line_len   ; A/X = len
set_cursor_col_ax:
  STAX16 CURSOR_COL16
  RTS

; X = 1 + pending repeats of the key in BUF_TEMP (set by insert_handle_key)
insert_move_count:
  JSR count_pending_key
  INX
  RTS
