; Normal mode shared utilities - zero-page variables, dispatch, cursor helpers,
; count prefix system, and common yank/delete operations.

  .zeropage

LAST_KEY:       .byte  ; Previous key for multi-key commands (dd, gg, yy, m, ')
LINE_LEN16:     .word  ; Cached length of current line (16-bit)
DISPATCH_PTR16: .word  ; Pointer into dispatch table during scan
JUMP_TARGET16:  .word  ; Target for indirect jump
COUNT16:        .word  ; Accumulated count (0 = no count entered)
COUNT_ACTIVE:   .byte  ; $FF if digits are being entered, $00 otherwise
NORMAL_TEMP:    .byte  ; Temp byte for normal mode operations
SCROLL_AMOUNT:  .byte  ; Sticky scroll amount for Ctrl-D/U (0 = half-page default)
BATCH_RESTORE_KEY: .byte ; Key to restore to LAST_KEY after batch (0 = none)
BATCH_EXTRA:       .byte ; Number of extra pairs found by batch_pending_pairs (0 = none)
DEL_BACK:          .byte ; $FF when batched_char_delete serves X (last press deleted the range's first char)

  .code

; --- Generic key dispatcher ---
; Input: A = low byte, X = high byte of dispatch table address
;        BUF_TEMP = key code to match
; Output: C = 0 if handler was called, C = 1 if no match
dispatch_key:
  STA DISPATCH_PTR16
  STX DISPATCH_PTR16 + 1
  LDY #0
.loop:
  LDA (DISPATCH_PTR16),Y
  BEQ dispatch_no_match
  CMP BUF_TEMP
  BEQ dispatch_fetch_jump
  INY
  INY
  INY
  JMP .loop

; Shared dispatch tail: fetch handler at Y+1/Y+2 and call it, return C=0
; (also used by dispatch_pending_key)
dispatch_fetch_jump:
  INY
  LDA (DISPATCH_PTR16),Y
  STA JUMP_TARGET16
  INY
  LDA (DISPATCH_PTR16),Y
  STA JUMP_TARGET16 + 1
  JSR .do_jump
  CLC
  RTS
.do_jump:
  JMP (JUMP_TARGET16)
dispatch_no_match:
  SEC
  RTS

; --- Pending key dispatcher ---
; Input: A = low byte, X = high byte of dispatch table address
;        LAST_KEY = first key, BUF_TEMP = second key
; Output: C = 0 if handler was called, C = 1 if no match
; Table format: 5-byte entries [last_key, second_key, flags, handler_lo, handler_hi]
;   second_key = 0 means wildcard (match any second key)
;   flags bit 0: call batch_pending_pairs before handler
;   Terminated by 0 byte
dispatch_pending_key:
  STA DISPATCH_PTR16
  STX DISPATCH_PTR16 + 1
  LDY #0
.loop:
  LDA (DISPATCH_PTR16),Y
  BEQ dispatch_no_match
  CMP LAST_KEY
  BNE .next5
  INY
  LDA (DISPATCH_PTR16),Y
  BEQ .matched
  CMP BUF_TEMP
  BNE .next4
.matched:
  INY
  LDA (DISPATCH_PTR16),Y
  LSR
  BCC .no_batch
  TYA
  PHA
  JSR batch_pending_pairs
  PLA
  TAY
.no_batch:
  JMP dispatch_fetch_jump
.next5:
  INY
.next4:
  INY
  INY
  INY
  INY
  JMP .loop

; --- Cursor and line utilities ---

; Check if cursor is within current line
; Returns: carry clear = cursor in range (LINE_LEN16 set)
;          carry set = line empty or cursor at/past end
; Clobbers: A, X
check_cursor_in_line:
  JSR get_line_len_z
  ; Empty line needs no separate test: cursor >= 0 = len bails below
  CMP16 CURSOR_COL16, LINE_LEN16
  BCS .bail
  CLC
  RTS
.bail:
  SEC
  RTS

get_current_line_len:
  LDAX16 FILE_LINE16
  JMP buf_get_line_len

; Get buffer pointer to start of current line into BUF_PTR16
get_current_line_ptr:
  LDAX16 FILE_LINE16
  JMP buf_get_line_ptr

; Get buffer pointer at cursor position on current line
; Sets BUF_PTR16 to start of FILE_LINE16 + CURSOR_COL16
; Clobbers A, X, Y
get_cursor_buf_ptr:
  JSR get_current_line_ptr
  CLC
  ADC16 CURSOR_COL16, BUF_PTR16, BUF_PTR16
  RTS

clamp_cursor_col:
  JSR get_line_len_z
  BEQ .set_zero
  SEC
  SBCI16 LINE_LEN16, 1, LINE_LEN16  ; LINE_LEN16 = len - 1
  CMP16 LINE_LEN16, CURSOR_COL16
  BCS .ok                ; len-1 >= cursor, cursor is fine
  CP16 LINE_LEN16, CURSOR_COL16
.ok:
  RTS
.set_zero:
  LDA #0
  STA_LH16 CURSOR_COL16
  RTS

; --- Shared vertical movement loops ---

; Move down X lines (clamped to last line)
; Input: X = number of lines to move
; Clobbers: A, X, BUF_TEMP, BUF_PTR16
move_down_x:
.loop:
  STX BUF_TEMP
  CLC
  ADCI16 FILE_LINE16, $0001, BUF_PTR16
  CMP16 BUF_PTR16, LINE_COUNT16
  BCS .done
  INC16 FILE_LINE16
  LDX BUF_TEMP
  DEX
  BNE .loop
.done:
  RTS

; Move up X lines (clamped to first line)
; Input: X = number of lines to move
; Clobbers: A, X, BUF_TEMP
move_up_x:
.loop:
  STX BUF_TEMP
  TST16 FILE_LINE16
  BEQ .done
  DEC16 FILE_LINE16
  LDX BUF_TEMP
  DEX
  BNE .loop
.done:
  RTS

; --- Shared horizontal movement loops ---

; Move left X positions, clamped to col 0
; Input: X = count. Clobbers: A, X
move_left_x:
  TST16 CURSOR_COL16
  BEQ .done
  JSR dec_cursor_col
  DEX
  BNE move_left_x
.done:
  RTS

; Move right X positions, clamped to LINE_LEN16
; Input: X = count, LINE_LEN16 = max col. Clobbers: A, X
move_right_x:
  CMP16 CURSOR_COL16, LINE_LEN16
  BCS .done
  JSR inc_cursor_col
  DEX
  BNE move_right_x
.done:
  RTS

; --- Count prefix helpers ---

; Check if key starts a multi-key combo by scanning the combo table
; Input: A = low byte, X = high byte of combo table address
;        BUF_TEMP = key code to match
; Output: C = 0 if valid first key (LAST_KEY set), C = 1 if not
; Respects READONLY: skips entries with flags bit 1 set
check_combo_first_key:
  STA DISPATCH_PTR16
  STX DISPATCH_PTR16 + 1
  LDY #0
.loop:
  LDA (DISPATCH_PTR16),Y
  BEQ .no_match
  CMP BUF_TEMP
  BNE .skip
  ; Key matches - check READONLY + editing flag
  LDA READONLY
  BEQ .found
  INY
  INY
  LDA (DISPATCH_PTR16),Y
  DEY
  DEY
  AND #$02
  BEQ .found
.skip:
  TYA
  CLC
  ADC #5
  TAY
  JMP .loop
.found:
  LDA BUF_TEMP
  STA LAST_KEY
  CLC
  RTS
.no_match:
  SEC
  RTS

; Get count and clamp to available lines from FILE_LINE16
; Output: BUF_TEMP16 = clamped count, LINE_LEN16 = FILE_LINE16 (line counter)
; Clobbers: A
get_count_clamp_lines:
  JSR get_count
  SEC
  SBC16 LINE_COUNT16, FILE_LINE16, BUF_LEN16
  CMP16 BUF_TEMP16, BUF_LEN16
  BCC .ok
  CP16 BUF_LEN16, BUF_TEMP16
.ok:
  CP16 FILE_LINE16, LINE_LEN16
  RTS

; --- Insert mode entry helpers ---

; Enter insert mode with render flag=1
enter_insert_mode_render:
  ; fall through

; Enter insert mode and clear count
enter_insert_mode:
  LDA #MODE_INSERT
  STA MODE
  LDA #0
  STA INSERT_CHANGED
  JMP clear_count

; Set RENDER_FLAG from A, then clear count state
set_render_clear_count:
  STA RENDER_FLAG
  ; fall through

; Clear count state: zeroes COUNT16, COUNT_ACTIVE, LAST_KEY
; If BATCH_RESTORE_KEY is set, restores it to LAST_KEY (for partial pair e.g. dddw)
clear_count:
  LDA #0
  STA_LH16 COUNT16
  STA COUNT_ACTIVE
  LDA BATCH_RESTORE_KEY
  STA LAST_KEY
  LDA #0
  STA BATCH_RESTORE_KEY
  STA BATCH_EXTRA
  RTS

; Move cursor to col 0, clamp, then clear count (shared terminal tail)
zero_col_clamp_clear:
  LDA #0
  STA_LH16 CURSOR_COL16
  ; fall through

; Clamp cursor column, then clear count state (shared terminal tail)
clamp_and_clear_count:
  JSR clamp_cursor_col
  JMP clear_count

; Accumulate digit in A ('0'-'9') into COUNT16
; COUNT16 = COUNT16 * 10 + digit
; If COUNT16 >= 1000, digit is ignored (prevents overflow)
; Clobbers A
count_accumulate_digit:
  ; Check if count already >= 1000 ($03E8)
  PHA                    ; Save digit char
  LDA COUNT16 + 1
  CMP #$03
  BCC .count_has_room
  BNE .count_at_limit
  LDA COUNT16
  CMP #$E8
  BCC .count_has_room
.count_at_limit:
  PLA                    ; Discard digit
  RTS
.count_has_room:
  PLA                    ; Restore digit char
  SEC
  SBC #'0'
  PHA                    ; Save digit

  ; Multiply COUNT16 by 10: COUNT16 * 8 + COUNT16 * 2
  ; Save original in BUF_LEN16
  CP16 COUNT16, BUF_LEN16

  ; *2
  ASL16 COUNT16
  ; *4
  ASL16 COUNT16
  ; *8
  ASL16 COUNT16

  ; original * 2
  ASL16 BUF_LEN16

  ; COUNT16 = COUNT16*8 + original*2
  CLC
  ADC16 COUNT16, BUF_LEN16, COUNT16

  ; Add digit
  PLA
  CLC
  ADCA16 COUNT16, COUNT16

  RTS

; Get effective count with pending key batching
; Gets count prefix, adds pending matching keys
; Input: BUF_TEMP = key code to match (set by normal_handle_key)
; Output: X = total count (count + pending), capped at 255
;         BATCH_EXTRA = pending key count (cleared later by clear_count;
;         callers that skip clear_count must not let it leak)
; Clobbers: A
get_batched_count:
  JSR get_count
  LDX BUF_TEMP16         ; X = count (low byte, capped at 255)
  STX BUF_DELTA
  JSR count_pending_key  ; X = pending matching keys
  STX BATCH_EXTRA
  TXA
  CLC
  ADC BUF_DELTA          ; Total = count + pending
  BCS .cap
  TAX
  RTS
.cap:
  LDX #$FF
  RTS

; Count extra pending paste keys and add to BUF_TEMP16
; Prerequisite: get_count already called (BUF_TEMP16 = count)
; Input: BUF_TEMP = key to match ('p' or 'P', already set by dispatch)
; Output: BUF_TEMP16 += extras, BATCH_EXTRA = extras count
; Clobbers: A, X
count_paste_extras:
  JSR count_pending_key      ; X = pending matching keys
  STX BATCH_EXTRA
  TXA
  BEQ .done
  CLC
  ADCA16 BUF_TEMP16, BUF_TEMP16
.done:
  RTS

; Get effective count in BUF_TEMP16, minimum 1
; If COUNT16 is 0, returns 1 (no count means "do once")
; Clobbers: A
get_count:
  LDA COUNT16
  ORA COUNT16 + 1
  BEQ set_buf_temp16_one     ; Zero = no count, return 1
  ; Copy COUNT16 to BUF_TEMP16
  LDA COUNT16
  STA BUF_TEMP16
  LDA COUNT16 + 1
  STA BUF_TEMP16 + 1
  RTS

; Set BUF_TEMP16 = 1
; Returns A = 0
set_buf_temp16_one:
  LDA #1
; Set BUF_TEMP16 = A (high byte 0)
; Returns A = 0
set_buf_temp16_a:
  STA BUF_TEMP16
  LDA #0
  STA BUF_TEMP16 + 1
  RTS

; --- Pair batching for 2-key commands ---

; Batch pending pairs of LAST_KEY + BUF_TEMP from the input stream
; Uses LAST_KEY (first key) and BUF_TEMP (second key) already set by
; pending_key_dispatch. Adds matched pairs to COUNT16.
; Sets BATCH_RESTORE_KEY if a partial pair was consumed.
; Clobbers: A, X
batch_pending_pairs:
  LDX #0                   ; X = extra pairs found
.loop:
  JSR key_ready
  CMP #$FF
  BNE .done                ; No key available, stop
  JSR get_key
  CMP LAST_KEY
  BNE .no_first_match      ; First key doesn't match, push back
  ; First key matches - need second key
  JSR key_ready
  CMP #$FF
  BNE .partial             ; No second key available
  JSR get_key
  CMP BUF_TEMP
  BNE .second_mismatch     ; Second key doesn't match
  ; Full pair matched
  INX
  CPX #BATCH_MAX
  BEQ .done
  JMP .loop
.second_mismatch:
  ; Push back the non-matching second key
  JSR unget_key
.partial:
  ; Save consumed first key for restore after command completes
  LDA LAST_KEY
  STA BATCH_RESTORE_KEY
  JMP .done
.no_first_match:
  ; Push back the non-matching key
  JSR unget_key
.done:
  STX BATCH_EXTRA
  ; Add X extra pairs to COUNT16
  TXA
  BEQ .no_add              ; No extra pairs, nothing to do
  ; Ensure COUNT16 >= 1 (the original command counts as 1)
  PHA                      ; Save extra count
  LDA COUNT16
  ORA COUNT16 + 1
  BNE .has_count
  LDA #1
  STA COUNT16              ; COUNT16 was 0, set to 1
.has_count:
  PLA                      ; Restore extra count
  CLC
  ADC COUNT16
  STA COUNT16
  LDA #0
  ADC COUNT16 + 1
  STA COUNT16 + 1
.no_add:
  RTS

; --- Common yank/delete operations ---

; Show yank overflow error: clear yank, show message, clear count
; Used when yank buffer is too full to complete an operation
show_yank_overflow:
  JSR yank_clear
  LDA #<str_yank_full
  LDX #>str_yank_full
  JSR show_message_ax
  JMP clear_count

; Yank then delete N lines starting at FILE_LINE16
; Input: BUF_TEMP16 = count of lines (from get_count)
; Returns carry set = yank overflow, carry clear = success
; On success: lines deleted, FILE_LINE16 clamped, YANK_LINES16 set
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_LEN16
yank_delete_current_lines:
  JSR yank_clear
  LDAX16 FILE_LINE16
  JSR yank_add_lines
  BCS .ydcl_overflow
  JSR undo_record_line_delete
  JSR delete_current_lines
  CLC
  RTS

.ydcl_overflow:
  SEC
  RTS

; Delete N lines starting at FILE_LINE16 without yanking
; Input: BUF_TEMP16 = count of lines (from get_count)
; Adjusts marks, deletes lines, clamps FILE_LINE16
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_LEN16
delete_current_lines:
  LDAX16 FILE_LINE16
  JSR mark_adjust_delete

  LDAX16 FILE_LINE16
  JSR buf_delete_lines

  ; Clamp file line if past end of file
  CMP16 FILE_LINE16, LINE_COUNT16
  BCC .dcl_ok
  SEC
  SBCI16 LINE_COUNT16, 1, FILE_LINE16
.dcl_ok:
  RTS

; Yank chars at cursor position then delete them
; Input: BUF_LEN16 = number of bytes to delete, cursor position set via CURSOR_COL16
; Yanks from cursor, deletes, rebuilds lines, sets MODIFIED
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16
yank_delete_at_cursor:
  JSR undo_record_char_delete
  PUSH16 BUF_LEN16           ; Save delete count
  JSR get_cursor_buf_ptr     ; BUF_PTR16 = cursor position
  CP16 BUF_PTR16, BUF_SRC16
  JSR yank_add_chars         ; Clobbers BUF_LEN16, BUF_PTR16
  POP16 BUF_LEN16            ; Restore delete count
  ; Fall through to delete_at_cursor

; Delete bytes at cursor position (no yank)
; Input: BUF_LEN16 = number of bytes to delete, cursor position set via CURSOR_COL16
; Shifts buffer, adjusts line table (incremental if no newlines), sets MODIFIED
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16
delete_at_cursor:
  JSR get_cursor_buf_ptr     ; BUF_PTR16 = cursor position
  ; Scan deleted range for newlines
  CP16 BUF_PTR16, BUF_DST16 ; BUF_DST16 = scan pointer
  LDA #0
  STA NORMAL_TEMP            ; 0 = no newlines found
  PUSH16 BUF_LEN16           ; Save delete count
.scan_nl:
  TST16 BUF_LEN16
  BEQ .scan_done
  LDY #0
  LDA (BUF_DST16),Y
  CMP #'\n'
  BNE .scan_next
  INC NORMAL_TEMP            ; Found newline
.scan_next:
  INC16 BUF_DST16
  DEC16 BUF_LEN16
  JMP .scan_nl
.scan_done:
  POP16 BUF_LEN16            ; Restore delete count
  ; Pre-compute old screen rows BEFORE shift (only when newlines found)
  LDA NORMAL_TEMP
  BEQ .no_precompute
  ; Walk cursor line + deleted lines to sum old screen rows
  ; NORMAL_TEMP = number of newlines = number of extra lines
  JSR set_render_line_to_cursor
  LDA #0
  STA SCROLL_DELTA            ; accumulator for old screen rows
  LDA NORMAL_TEMP
  STA SCROLL_AMOUNT           ; loop counter (lines after cursor)
  ; First: cursor line
  JSR render_line_rows
  STA SCROLL_DELTA
  ; Then: each deleted line
.precomp_walk:
  LDA SCROLL_AMOUNT
  BEQ .precomp_done
  INC16 RENDER_LINE16
  JSR render_line_rows
  CLC
  ADC SCROLL_DELTA
  STA SCROLL_DELTA
  DEC SCROLL_AMOUNT
  JMP .precomp_walk
.precomp_done:
.no_precompute:
  JSR get_cursor_buf_ptr     ; Recompute BUF_PTR16 (scan clobbered BUF_DST16)
  JSR buf_shift_left_16
  LDA NORMAL_TEMP
  BNE .full_rebuild
  ; Incremental: negate BUF_LEN16 into BUF_SRC16
  LDA #0
  SEC
  SBC BUF_LEN16
  STA BUF_SRC16
  LDA #0
  SBC BUF_LEN16 + 1
  STA BUF_SRC16 + 1
  JSR buf_adjust_lines_apply
  JMP .done
.full_rebuild:
  JSR buf_rebuild_lines
  ; Adjust marks for deleted newlines (NORMAL_TEMP = count)
  LDA NORMAL_TEMP
  JSR set_buf_temp16_a
  LDAX16 FILE_LINE16
  SEC
  JSR mark_adjust_col
  ; Signal line-delete scroll, skip cursor row in scroll region
  JSR file_line_rows
  STA DELETE_SCREEN_ROWS     ; Cursor line screen rows (new)
  ; Compute SCROLL_DELTA = old_total - new_cursor_rows
  LDA SCROLL_DELTA            ; old total screen rows
  SEC
  SBC DELETE_SCREEN_ROWS
  STA SCROLL_DELTA            ; pre-computed scroll displacement
  LDA #$08
  STA RENDER_FLAG            ; Line-delete, skip cursor row, repaint cursor
.done:
  LDA #$FF
  STA MODIFIED
  RTS

; --- Operator dispatch ---

OP_YANK   = 0
OP_DELETE = 1
OP_CHANGE = 2

; Apply operator to character range at cursor
; Input: A = operator (OP_YANK, OP_DELETE, OP_CHANGE)
;        BUF_LEN16 = byte count of range
;        Cursor at start of range (CURSOR_COL16, FILE_LINE16)
; OP_YANK:   yank range, done
; OP_DELETE:  yank range, delete, clamp cursor
; OP_CHANGE:  yank range, delete, enter insert mode
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16
apply_char_operator:
  CMP #OP_YANK
  BNE .do_delete
  ; Yank only: no delete, no MODIFIED
  JSR get_cursor_buf_ptr
  CP16 BUF_PTR16, BUF_SRC16
  JSR yank_add_chars
  RTS
.do_delete:
  PHA                          ; Save operator on stack
  JSR yank_delete_at_cursor
  PLA                          ; Restore operator
  CMP #OP_CHANGE
  BEQ .change
  ; OP_DELETE: clamp cursor
  JSR clamp_cursor_col
  RTS
.change:
  JMP enter_insert_mode_render

; --- Shared batched character delete (for x and X commands) ---

; Batched character delete for x (batched_char_delete) and X
; (batched_char_delete_back, cursor already moved to the range start).
; When batched, the register gets what the last key press deleted: the
; range's last char for x, its first char for X.
; Input: BUF_TEMP16 = total count, BATCH_EXTRA = # of extra batched units (0 = no batching)
;        LINE_LEN16 = line length (from check_cursor_in_line)
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_LEN16
batched_char_delete_back:
  LDA #$FF
  BNE bcd_start             ; Always taken
batched_char_delete:
  LDA #0
bcd_start:
  STA DEL_BACK
  LDA BATCH_EXTRA
  BNE .batched

  ; --- Non-batched: compute full range, yank+delete all ---
  LDX BUF_TEMP16
  JSR compute_char_range_forward
  BCS .done
  JSR set_shift_delete
  LDA #OP_DELETE
  JSR apply_char_operator
  JMP .finish

.batched:
  ; --- Batched: compute full range, yank last-deleted char, delete all ---
  LDX BUF_TEMP16
  JSR compute_char_range_forward
  BCS .done
  JSR set_shift_delete
  ; Yank 1 char at cursor + range - 1 (x) or at cursor (X)
  PUSH16 BUF_LEN16              ; Save full range
  JSR yank_clear
  SEC
  SBCI16 BUF_LEN16, 1, BUF_LEN16
  LDA DEL_BACK
  BEQ .yank_offset_ok
  LDA #0
  STA_LH16 BUF_LEN16
.yank_offset_ok:
  CLC
  ADC16 CURSOR_COL16, BUF_LEN16, BUF_LEN16  ; BUF_LEN16 = col of yanked char
  PUSH16 CURSOR_COL16
  CP16 BUF_LEN16, CURSOR_COL16  ; Move cursor to yanked char
  JSR get_cursor_buf_ptr         ; BUF_PTR16 = address of yanked char
  CP16 BUF_PTR16, BUF_SRC16
  LDA #1
  STA BUF_LEN16
  LDA #0
  STA BUF_LEN16 + 1
  JSR yank_add_chars
  POP16 CURSOR_COL16             ; Restore original cursor
  POP16 BUF_LEN16               ; Restore full range
  ; Record undo before deleting
  JSR undo_record_char_delete
  ; Delete full range in single operation
  JSR delete_at_cursor

.finish:
  JSR clamp_cursor_col
.done:
  JMP clear_count

; ICH/DCH hint for deleting BUF_LEN16 (<= 255) chars at the cursor
; Clobbers: A
set_shift_delete:
  LDA #0
  STA SHIFT_WRITE
  SEC
  SBC BUF_LEN16
  STA SHIFT_NET
  RTS
