; Insert mode handler
;
; In insert mode:
;   - Printable characters ($20-$7E) and Tab are inserted at the cursor
;   - Enter ($0D) inserts a newline
;   - Backspace ($08) deletes the char before the cursor or joins lines
;   - Delete ($88) deletes the char at the cursor or joins lines forward
;   - Ctrl-F and Ctrl-B are inserted as chars, as in vim
;   - Other keys (ESC, arrows, Home/End, PgUp/PgDn, Ctrl-arrows) are
;     dispatched through insert_keys; ESC returns to normal mode
;
; insert_handle_key collects a batch of mixed editing keys (up to
; BATCH_MAX) and consolidates it on the fly into canonical form
;   [back N] [insert BATCH_BUF] [fwd N]
; which it then executes with a single buffer shift.

  .code

; --- Dispatch table ---

insert_keys:
  .byte KEY_ESC     .word insert_exit
  .byte KEY_UP      .word normal_move_up      ; As k and j
  .byte KEY_DOWN    .word normal_move_down
  .byte KEY_LEFT    .word normal_move_left    ; As h and l (clamped for
  .byte KEY_RIGHT   .word normal_move_right   ; the mode)
  .byte KEY_HOME    .word normal_line_start   ; Col 0 (no count in insert mode)
  .byte KEY_END     .word normal_line_end     ; Col = len (and j/k stick there)
  .byte KEY_PGDN    .word normal_page_down    ; These land on the first
  .byte KEY_PGUP    .word normal_page_up      ; non-blank: no insert clamp
  .byte KEY_WORD_FWD  .word insert_word_fwd
  .byte KEY_WORD_BACK .word insert_word_back
  .byte 0           ; End sentinel

; Exit insert mode, return to normal mode (the undo record of the typing
; stays for u)
insert_exit:
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
;   Y = remaining capacity - 1 (counts down from BUF_DELTA: BATCH_MAX - 1,
;       or the free bytes - 1 when fewer)
;
; Execution phase variables:
;   BUF_DELTA      = insert_len
;   BUF_TEMP16.lo  = back (clamped to the bytes before the cursor)
;   BUF_TEMP       = fwd_actual (the forward scan never takes the buffer's
;                    final '\n')
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
  STA BUF_TEMP              ; key code (for dispatch_key / get_count_pending16)
  ; --- Collection phase ---
  LDX #0                    ; BATCH_BUF write index
  STX BUF_TEMP16            ; back = 0
  STX BUF_TEMP16 + 1        ; fwd = 0
  STX BATCH_BUF             ; Stays 0 unless a char is typed (even if erased)
  ; Take no more keys than there are free bytes, so that the batch fits
  ; (it grows by at most one byte a key): a char that does not fit comes
  ; alone and is refused as when typed alone, and the keys after it wait
  ; their turn
  LDY #BATCH_MAX - $01      ; remaining capacity - 1
  LDA BUF_END16
  CMP #<TEXT_LIMIT - BATCH_MAX + $01
  LDA BUF_END16 + 1
  SBC #>TEXT_LIMIT - BATCH_MAX + $01
  BCC .have_cap             ; BATCH_MAX or more bytes free
  LDA BUF_END16             ; TEXT_LIMIT is page aligned, so free - 1 =
  EOR #$FF                  ; $FF - BUF_END16.lo: -1 when none (the batch
  TAY                       ; then takes one key)
.have_cap:
  STY BUF_DELTA             ; (for the first-key test)
  ; Likewise take no more Enter keys than there are lines left, so that
  ; the batch never passes the line limit (a BS or DEL that joins lines
  ; is not counted: the Enters after it wait for the next batch, which
  ; counts the lines anew): NORMAL_TEMP = the lines left, 127 for 127 or
  ; more (a batch has fewer keys)
  LDA LINE_COUNT16 + 1
  CMP #>MAX_LINES
  BCC .plenty               ; Fewer than $300 lines
  LDA LINE_COUNT16
  EOR #$FF                  ; $3FF - LINE_COUNT16 (<<MAX_LINES is $FF)
  BPL .have_room
.plenty:
  LDA #$7F
.have_room:
  STA NORMAL_TEMP
  LDA BUF_TEMP
.collect_key:
  CMP #KEY_ENTER
  BEQ .key_enter
  CMP #KEY_BS
  BEQ .key_bs
  CMP #KEY_DEL
  BEQ .key_del
  CMP #KEY_TAB
  BEQ .key_printable
  ; Ctrl-F and Ctrl-B go in as chars, as in vim (PgDn and PgUp page)
  CMP #$06
  BEQ .key_printable
  CMP #$02
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
  DEC NORMAL_TEMP           ; The lines left
  BPL .enter_fits
  CPY BUF_DELTA
  BNE .end_batch            ; It waits its turn (A = KEY_ENTER)
  LDY #0                    ; The first key: alone, refused as when typed
.enter_fits:                ; alone
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
  DEY
  BMI .collect_done         ; (the capacity is at most BATCH_MAX)
  JSR key_peek              ; A = next key
  BCC .collect_done
  INC HAS_KEY_DECODED       ; Consume it ($FF -> $00)
  BEQ .collect_key          ; Always taken (INC gave $00)

.key_other:
  CPY BUF_DELTA
  BNE .end_batch
  ; The first key is not an editing key: dispatch it (BUF_TEMP = key).
  ; As in vim, a move ends the undo segment, and the next change starts a
  ; new one: Home and End always, other keys when the cursor moved (one
  ; that fails does not)
  LDA BUF_TEMP
  AND #$FE
  EOR #KEY_HOME              ; 0: Home or End
  PHA
  LDA #<insert_keys
  LDX #>insert_keys
  JSR dispatch_key
  PLA
  BEQ .end_segment           ; (A = 0)
  JSR cursor_moved
  BEQ .kept
  LDA #0
.end_segment:
  STA INSERT_SEG
.kept:
  RTS
.end_batch:
  JSR unget_key

.collect_done:
  ; X = insert_len, BUF_TEMP16.lo = back, BUF_TEMP16.hi = fwd
  STX BUF_DELTA

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
  JSR ptr_to_src

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
  BEQ .net_zero
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
.batch_full:                 ; (the buffer only overflows by a lone key)
  JMP show_buffer_full_msg

.net_zero:
  LDA BUF_DELTA              ; insert_len (= total_delete)
  BNE .do_copy
  ; Nothing deleted and nothing inserted.  Chars typed and erased again
  ; changed the buffer twice, as when typed one at a time: mark it
  ; modified, with nothing to draw, and keep the empty change for u.
  ; Else (a BS at the buffer start, a DEL on the final newline) nothing
  ; changed, as in vim
  CMP BATCH_BUF              ; C = 0 if a char was typed
  BCS .no_change
  LSR EMPTY_BUF              ; The line is a line of the text now
  JSR insert_segment
  JMP set_modified
.no_change:
  RTS

.do_copy:
  JSR insert_segment         ; The batch goes in: keep it for undo
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
  RTS

  ; ========================================
  ; Newlines path: rebuild + mark adjust
  ; ========================================
.newlines_path:
  ; A pure batch typed and deleted only newlines, so the text of its lines
  ; is as it was: INSERT_LINE_COUNT = $FF (0 from main_loop) for the
  ; Enter and join repaints that the scroll alone draws
  LDA BUF_DELTA              ; insert_len
  CMP NORMAL_TEMP            ; ins_nl (C = 1 if equal)
  BNE .not_pure
  LDA BUF_TEMP16             ; back
  ADC BUF_TEMP               ; + fwd_actual + 1 (C = 0: at most 65)
  SBC LINE_LEN16             ; - back_nl - 1 (C = 1: back >= back_nl)
  SBC LINE_LEN16 + 1         ; - fwd_nl = the other chars deleted
  BNE .not_pure
  DEC INSERT_LINE_COUNT
.not_pure:
  ; BUF_LEN16 = cursor_buf_pos = delete_start + insert_len (survives the
  ; rebuild and the mark adjustment)
  LDA BUF_DELTA
  CLC
  ADCA16 BUF_PTR16, BUF_LEN16

  ; FILE_LINE16 = first merged line (the line holding delete_start),
  ; where the line table changes from
  SEC
  SBC16_8 FILE_LINE16, LINE_LEN16, FILE_LINE16
  JSR buf_rebuild_lines

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
  ; Newlines inserted.  Also merged: full redraw
  LDA LINE_LEN16             ; back_nl
  ORA LINE_LEN16 + 1         ; fwd_nl
  BNE .full_redraw
  ; A pure Enter batch at the end of the line (the cursor line is empty:
  ; INSERT_LINE_COUNT = $7F) or at its start (the first changed column
  ; is 0: $FF) is drawn by the scroll alone; any other keeps 0
  LDA INSERT_LINE_COUNT
  BEQ .enter_flag            ; not pure
  LDY #0
  LDA (BUF_PTR16),Y          ; the char at the cursor (column 0)
  CMP #'\n'
  BEQ .enter_at_end
  LDA RENDER_FROM_COL16
  ORA RENDER_FROM_COL16 + 1
  BEQ .enter_flag            ; at the start: $FF
  INC INSERT_LINE_COUNT      ; mid-line: 0 (and the LSR keeps it)
.enter_at_end:
  LSR INSERT_LINE_COUNT
.enter_flag:
  LDA #RF_ENTER              ; Line-insert above cursor scroll
  BNE .set_flag              ; Always taken

  ; Lines merged, none inserted: the joined line changed from where the
  ; batch began, before the text it typed (RF_JOIN)
.joined:
  LDA BUF_DELTA              ; insert_len
  JSR set_render_from_before_cursor
  LDA LINE_LEN16             ; back_nl
  BEQ .join_at_eol           ; forward newlines deleted only
  ; --- Backward newlines deleted.  Forward ones too: full redraw ---
  LDA LINE_LEN16 + 1         ; fwd_nl
  BNE .full_redraw
  ; A pure join leaves the cursor line's text as it was when the cursor
  ; ends at column 0 (the lines above were empty) or at the end of the
  ; line (the lines below were): it is a dd of those empty lines, a row
  ; each (RF_DEL), from the line's first row or from below it
  LDA CURSOR_COL16
  ORA CURSOR_COL16 + 1
  BNE .join_at_eol
  BIT INSERT_LINE_COUNT
  BMI .pure_join             ; (A = 0: from the line's first row)
  BPL .join_flag             ; Always taken
.join_at_eol:
  LDA INSERT_LINE_COUNT
  BEQ .join_flag             ; not pure
  JSR get_current_line_len   ; A = low, X = high
  CMP CURSOR_COL16
  BNE .join_flag
  CPX CURSOR_COL16 + 1
  BNE .join_flag
  JSR file_line_rows         ; from below the line's rows
.pure_join:
  STA DELETE_SCREEN_ROWS
  LDA LINE_LEN16
  ORA LINE_LEN16 + 1         ; back_nl or fwd_nl (the other is 0)
  STA SCROLL_DELTA
  LDA #RF_DEL
  BNE .set_flag              ; Always taken
.join_flag:
  LDA #RF_JOIN               ; Line-delete with displacement-based scroll
  BNE .set_flag              ; Always taken
.full_redraw:
  ; The batch joined lines and split them (or joined them both ways): the
  ; lines above the cursor line changed too, which a current-line redraw
  ; misses when the line count comes out the same: full redraw (rare,
  ; mixed type-ahead).  A pure batch put its newlines back where they
  ; were, or changed the line count (render_decide then redraws in full
  ; anyway): RF_AUTO draws only what moved
  LDA INSERT_LINE_COUNT
  EOR #$FF                   ; pure ($FF): RF_AUTO, else RF_FULL
.set_flag:
  JMP .set_render_flag

; Keep the undo record of the insert segment (the typing since insert
; mode began, or since a move) for a batch that goes in.  The record
; (UNDO_INSERT) is where the segment starts and the length of the text
; typed there, which ends at the cursor: the cursor moves only by the
; typing in a segment.  On entry FILE_LINE16/CURSOR_COL16 = the cursor
; before the batch, BUF_TEMP16.lo = back, BUF_TEMP = fwd_actual,
; BUF_DELTA = insert_len.  A BS of text from before the segment's start
; or a DEL of text after the cursor is not kept: it clears the undo, and
; the rest of the segment's changes too (INSERT_SEG $7F), as the typing
; after a change command does
insert_segment:
  LDA INSERT_SEG
  BMI .open                  ; $FF: the record is kept
  BNE .clear                 ; Not kept
  STA UNDO_INS_OPEN          ; A new segment (A = 0: not o or O)
  JSR insert_seg_start
.open:
  LDA BUF_TEMP               ; fwd_actual
  BNE .not_kept
  ; len = len - back + insert_len, unless back passes the start
  LDA UNDO_INS_LEN16
  SEC
  SBC BUF_TEMP16             ; - back
  TAX
  LDA UNDO_INS_LEN16 + 1
  SBC #0
  BCC .not_kept              ; back > len
  STA UNDO_INS_LEN16 + 1
  TXA
  CLC
  ADC BUF_DELTA              ; + insert_len
  STA UNDO_INS_LEN16
  BCC .done
  INC UNDO_INS_LEN16 + 1
.done:
  RTS
.not_kept:
  LSR INSERT_SEG             ; $7F
.clear:
  JMP undo_clear

; Start an insert segment at the cursor, with no text yet: its record
; replaces the one before, and the typing extends it.  It starts once
; its first change has gone in: whether the buffer had lines before it
; is in EMPTY_BUF's bit 6 (the change cleared bit 7).  Returns A = 0
insert_seg_start:
  LDA #$FF
  STA INSERT_SEG
  LDA #UNDO_INSERT
  STA UNDO_TYPE
  JSR undo_record_pos        ; A = 0
  ASL UNDO_WAS_EMPTY         ; Bit 6: before the change
  STA_LH16 UNDO_INS_LEN16
  RTS

; Word motion handlers in insert mode, counted with pending repeats of
; the same key.  Word motions stay within 0..len (in insert mode the
; cursor may sit one past the last char), so need no clamp.  (The arrow
; keys run the code of h, l, j and k, whose clamp_cursor_col keeps to
; the line end in insert mode.)
insert_word_fwd:
  JSR get_count_pending16
  JMP word_forward_x

insert_word_back:
  JSR get_count_pending16
  JMP word_backward_x



