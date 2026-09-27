; Normal mode shared utilities - dispatch, cursor helpers,
; count prefix system, and common yank/delete operations.

; (zero-page variables: zp.asm)

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
  BNE .loop                  ; Always (tables are < 256 bytes)

; --- Pending key dispatcher ---
; Input: A = low byte, X = high byte of dispatch table address
;        LAST_KEY = first key, BUF_TEMP = second key
; Output: C = 0 if handler was called, C = 1 if no match
; Table format: 5-byte entries [last_key, second_key, flags, handler_lo, handler_hi]
;   second_key = 0 means wildcard (match any second key)
;   flags bit 0: take the typed-ahead pairs and run the handler once per
;     press (dispatch_replay)
;   Terminated by 0 byte
dispatch_pending_key:
  STA DISPATCH_PTR16
  STX DISPATCH_PTR16 + 1
  LDY #0
.loop:
  LDA (DISPATCH_PTR16),Y
  BEQ dispatch_no_match
  INY
  CMP LAST_KEY
  BNE .next
  LDA (DISPATCH_PTR16),Y
  BEQ .matched               ; Wildcard second key
  CMP BUF_TEMP
  BEQ .matched
.next:
  INY
  INY
  INY
  INY
  BNE .loop                  ; Always (tables are < 256 bytes)
.matched:
  INY
  LDA (DISPATCH_PTR16),Y     ; Flags
  LSR
  BCC dispatch_fetch_jump
  JSR batch_pending_pairs    ; X = pairs taken; preserves Y
  TXA
  BNE dispatch_replay
  ; fall through

; Shared dispatch tail (dispatch_key, dispatch_pending_key): fetch the
; handler at Y+1/Y+2 and call it, return C=0
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

; Check if key starts a multi-key combo by scanning the combo table
; Input: A = low byte, X = high byte of combo table address
;        BUF_TEMP = key code to match
; Output: C = 0 if valid first key (LAST_KEY set), C = 1 if not
; Respects READONLY: skips entries with flags bit 1 set
; A second key that is already typed is handled at once, so the pending
; first key gets no frame of its own (dw, dd, gg, ra...).  Only a first
; key that has changed nothing yet is batched this way: the first key of
; a partial pair, left pending after its command, waits for a render
check_combo_first_key:
  STA DISPATCH_PTR16
  STX DISPATCH_PTR16 + 1
  LDY #0
.loop:
  LDA (DISPATCH_PTR16),Y
  BEQ dispatch_no_match
  INY
  INY                        ; Y -> flags
  CMP BUF_TEMP
  BNE .skip
  ; Key matches - check READONLY + editing flag
  LDA READONLY
  BEQ .found
  LDA (DISPATCH_PTR16),Y
  AND #$02
  BEQ .found
.skip:
  INY
  INY
  INY
  BNE .loop                  ; Always (tables are < 256 bytes)
.found:
  LDA BUF_TEMP
  STA LAST_KEY
  JSR key_peek
  BCS .second                ; The second key is typed already
  ASL CURSWANT_KEEP          ; A pending first key changes nothing (yet)
  CLC
  RTS
.second:
  JSR get_key
  JSR normal_handle_key      ; LAST_KEY set: dispatches the pair
  CLC
  RTS
; No match (dispatch_key, dispatch_pending_key, check_combo_first_key)
dispatch_no_match:
  SEC
  RTS

; Run the handler once per typed-ahead press, exactly as if the keys had
; been typed one at a time, with a single render afterwards.  For dw, db
; and de, whose N presses differ from a count of N (a press stops at a
; line end or on an empty line, and u undoes only the last one).
; The first press takes the typed count, the others none (each press
; ends in clear_count).
; Input: Y = the entry's flags index, A = BATCH_EXTRA = extra presses (> 0)
; Output: C = 0 (handler called)
dispatch_replay:
  PHA                        ; Presses left after the next one
  LDA BATCH_RESTORE_KEY      ; A partial pair's first key: pending after
  PHA                        ; the last press
  TYA
  PHA                        ; Flags index
  LDA #0
  STA BATCH_RESTORE_KEY
  STA BATCH_EXTRA            ; Each press on its own (dd for a linewise dw)
.press:
  JSR snapshot_cursor        ; Where this press starts (range_yank_full)
  TSX
  LDY $0101,X                ; Flags index
  JSR dispatch_fetch_jump
  TSX
  DEC $0103,X
  BPL .press
  PLA
  PLA
  STA LAST_KEY               ; (clear_count left it 0)
  PLA
  ; A press that set a render flag (it joined lines) left scroll hints
  ; for itself only: repaint everything
  LDA RENDER_FLAG
  BEQ .rendered
  LDA #RF_FULL
  STA RENDER_FLAG
.rendered:
  CLC
  RTS

; --- Cursor and line utilities ---

; Check if cursor is within current line
; Returns: carry clear = cursor in range (LINE_LEN16 set)
;          carry set = line empty or cursor at/past end
; Clobbers: A, X
check_cursor_in_line:
  JSR get_line_len_z
  ; Empty line needs no separate test: cursor >= 0 = len sets carry
  CMP16 CURSOR_COL16, LINE_LEN16
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

; BUF_SRC16 = BUF_PTR16 = buffer address at the cursor.  Clobbers A, X, Y
get_cursor_src:
  JSR get_cursor_buf_ptr
  CP16 BUF_PTR16, BUF_SRC16
  RTS

; Clamp CURSOR_COL16 to the line's last char (0 on an empty line)
; Output: LINE_LEN16 = line length.  Clobbers: A, X, Y
clamp_cursor_col:
  JSR check_cursor_in_line
  BCC .ok                    ; Cursor inside the line
  CP16 LINE_LEN16, CURSOR_COL16
  ORA CURSOR_COL16           ; A = high byte: Z = empty line (col 0)
  BEQ .ok
  JMP dec_cursor_col         ; col = len - 1
.ok:
  RTS

; --- Shared vertical movement ---

; BUF_TEMP16 = the count (1 with none, as in insert mode) plus the
; typed-ahead presses of the same key (BUF_TEMP): j, k and the insert-
; mode motions.  X = its low byte (in insert mode, the presses).
; Clobbers A
get_count_pending16:
  JSR get_count
  JSR count_pending_key      ; X = the presses
  TXA
  ADDA16 BUF_TEMP16
  TAX
  RTS

; Move down BUF_TEMP16 lines, clamped to the last line (the count is at
; most 64,000, so the sum stays within 16 bits).  Clobbers: A
move_down16:
  CLC
  ADC16 FILE_LINE16, BUF_TEMP16, FILE_LINE16
  ; fall through

; Clamp FILE_LINE16 to the last line.  Clobbers: A
clamp_file_line:
  CMP16 FILE_LINE16, LINE_COUNT16
  BCC .ok
  SEC
  SBCI16 LINE_COUNT16, 1, FILE_LINE16
.ok:
  RTS

; Move up BUF_TEMP16 lines, clamped to the first line.  Clobbers: A, X
move_up16:
  LDX #FILE_LINE16
; The 16-bit zero-page value at X -= BUF_TEMP16, clamped to 0.
; Clobbers: A
sub_count_x:
  SEC
  LDA $00,X
  SBC BUF_TEMP16
  STA $00,X
  LDA $01,X
  SBC BUF_TEMP16 + 1
  STA $01,X
  BCS .ok
  LDA #0
  STA $00,X
  STA $01,X
.ok:
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

; Move right X positions, clamped to LINE_LEN16 (insert-mode Right)
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

; Get count, clamped to the lines from FILE_LINE16 to the end, for the
; line commands (dd, cc, S, yy, >>, <<), which call it first.  On the
; last line a count of 2 or more fails, as in vim (it moves down count
; - 1 lines first): the command ends there (end_command)
; Output: BUF_TEMP16 = clamped count, BUF_LEN16 = the lines left.
; Clobbers: A, X
get_count_clamp_lines:
  JSR get_count
  JSR lines_left
  BNE .clamp                 ; Not the last line
  LDA COUNT16
  LSR
  ORA COUNT16 + 1
  BNE end_command            ; A count of 2 or more
.clamp:
  CMP16 BUF_TEMP16, BUF_LEN16
  BCC .ok
  CP16 BUF_LEN16, BUF_TEMP16
.ok:
  RTS

; BUF_LEN16 = the lines from the cursor's to the end, Z set if the
; cursor is on the last line.  Clobbers A, X
lines_left:
  SEC
  SBC16 LINE_COUNT16, FILE_LINE16, BUF_LEN16
  LDX BUF_LEN16 + 1
  BNE .done
  LDX BUF_LEN16
  DEX
.done:
  RTS

; --- Insert mode entry helpers ---

; Enter insert mode and clear count
enter_insert_mode:
  LDA #MODE_INSERT
  STA MODE
  LDA #0
  STA INSERT_CHANGED
  JMP clear_count

; h and l: X = the count (and the typed-ahead presses), NORMAL_TEMP =
; the column's low byte, which tells h_l_done whether they moved (at
; most 255 columns)
h_l_setup:
  LDA CURSOR_COL16
  STA NORMAL_TEMP
  JMP get_batched_count

; h and l that could not move (vim beeps) keep the remembered column
h_l_done:
  LDA CURSOR_COL16
  CMP NORMAL_TEMP
  BNE clear_count
  BEQ keep_clear_count       ; Always

; End the command that called the routine that jumps here, which has
; pushed nothing (a command that fails: drop the return into it), as
; keep_clear_count
end_command:
  PLA
  PLA

; A command that did nothing (it failed, or it leaves the cursor and the
; text alone: m, and : commands but those that move the cursor) keeps the
; remembered column, as vim does, then clears the count state
keep_clear_count:
  ASL CURSWANT_KEEP
  JMP clear_count

; Set RENDER_FLAG from A, then clear count state
set_render_clear_count:
  STA RENDER_FLAG
  ; fall through

; Clear count state: zeroes COUNT16, LAST_KEY
; If BATCH_RESTORE_KEY is set, restores it to LAST_KEY (for partial pair e.g. dddw)
clear_count:
  LDA BATCH_RESTORE_KEY
  STA LAST_KEY
  LDA #0
  STA_LH16 COUNT16
  STA BATCH_RESTORE_KEY
  RTS

; $ and End (both modes): remember a column past any line end, so that j
; and k go to the end of each line too
; A count first goes down count - 1 lines (clamped to the last line), as
; in vim, where it fails on the last line itself (the column is
; remembered all the same: vert_moved)
normal_line_end:
  LDA #$FF
  STA_LH16 CURSWANT16
  JSR get_count
  JSR dec_buf_temp16
  BEQ vert_keep              ; No count, or 1: this line
  JSR move_down16
  JMP vert_moved

; Vertical move tail (j, k and Up/Down in both modes): the cursor goes
; to the remembered column (vim's curswant), clamped to the line for the
; mode.  A run of vertical keys remembers the column the cursor had at
; its start, which the previous key tells by leaving CURSWANT_KEEP 0
; (main_loop halves it for every key; a vertical move sets 2, and a key
; that changes nothing, a count digit, ESC or a pending first key,
; doubles it back); $ and End remember one past any line end.  A move
; that left the cursor on its line (j or N$ on the last line, k on the
; first) failed, as in vim, and leaves the column alone: only the
; remembered column counts
vert_col_clamp:
  LDA CURSWANT_KEEP
  BNE vert_moved
  CP16 CURSOR_COL16, CURSWANT16  ; A new run: remember the column
vert_moved:
  LDX #2
  STX CURSWANT_KEEP
  LDA FILE_LINE16
  CMP SNAP_LINE16
  BNE vert_to_col
  LDA FILE_LINE16 + 1
  CMP SNAP_LINE16 + 1
  BEQ clear_count                ; The cursor did not move: it failed
vert_keep:
  LDA #2
  STA CURSWANT_KEEP
vert_to_col:
  CP16 CURSWANT16, CURSOR_COL16
; Clamp the cursor column for the mode (normal: then clear the count)
clamp_for_mode:
  LDA MODE
  BEQ clamp_and_clear_count  ; Normal mode: onto the last char
  JMP clamp_cursor_col_insert ; Insert mode: up to the line end

; Clamp cursor column, then clear count state (shared terminal tail)
clamp_and_clear_count:
  JSR clamp_cursor_col
  JMP clear_count

; Accumulate the digit value in A (0-9) into COUNT16: COUNT16 =
; COUNT16 * 10 + digit, through mul10_add (so up to 63999)
; Clobbers A, Y, BUF_LEN16, BUF_DST16
count_accumulate_digit:
  TAY
  CP16 COUNT16, BUF_LEN16
  TYA
  JSR mul10_add
  CP16 BUF_LEN16, COUNT16
  RTS

; BUF_LEN16 = BUF_LEN16 * 10 + A (a digit value, 0-9), unless BUF_LEN16
; is 6400 or more: then the digit is ignored, so the value stays within
; 16 bits (at most 63999 before it stops: past every line, and every
; count, that matters).  Clobbers A, Y, BUF_DST16
mul10_add:
  LDY BUF_LEN16 + 1
  CPY #>6400
  BCS .done
  PHA
  ASL16 BUF_LEN16
  CP16 BUF_LEN16, BUF_DST16  ; x2
  ASL16 BUF_LEN16
  ASL16 BUF_LEN16            ; x8
  CLC
  ADC16 BUF_LEN16, BUF_DST16, BUF_LEN16
  PLA
  ADDA16 BUF_LEN16
.done:
  RTS

; Get effective count with pending key batching
; Gets the count prefix (capped at 255), adds pending matching keys
; Input: BUF_TEMP = key code to match (set by normal_handle_key)
; Output: X = total = count + pending keys (1 to 255)
;         BUF_DELTA = count, BATCH_EXTRA = pending key count
; Clobbers: A
get_batched_count:
  JSR get_count_x        ; X = count (capped at 255)
  STX BUF_DELTA
  ; Pending keys join only while the total fits in a byte; from a count
  ; of 256 - BATCH_MAX on they stay queued and run one at a time
  LDA #0
  CPX #256 - BATCH_MAX
  BCS .no_batch
  JSR count_pending_key  ; X = pending matching keys
  TXA
.no_batch:
  STA BATCH_EXTRA
  CLC
  ADC BUF_DELTA          ; Total = count + pending
  TAX
  RTS

; Get the count in X, capped at 255, for the commands that loop on an
; 8-bit count (BUF_TEMP16's low byte = X)
; Clobbers: A
get_count_x:
  JSR get_count
  LDX BUF_TEMP16
  LDA BUF_TEMP16 + 1
  BEQ .fits
  LDX #$FF
  STX BUF_TEMP16
.fits:
  RTS

; Get effective count in BUF_TEMP16, minimum 1
; If COUNT16 is 0, returns 1 (no count means "do once")
; Clobbers: A
get_count:
  LDA COUNT16
  STA BUF_TEMP16
  ORA COUNT16 + 1
  BEQ set_buf_temp16_one     ; Zero = no count, return 1
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
; pending_key_dispatch.  Leaves COUNT16 alone: each caller applies the
; pairs its own way.
; Sets BATCH_RESTORE_KEY if a partial pair was consumed.
; batch_pending_pairs_upto: X = most pairs to take (batch_pending_pairs:
; BATCH_MAX)
; Output: X = BATCH_EXTRA = pairs taken
; Clobbers: A.  Preserves Y
batch_pending_pairs:
  LDX #BATCH_MAX
batch_pending_pairs_upto:
  STX BATCH_EXTRA          ; The limit, until it becomes the pairs taken
  LDX #0                   ; X = extra pairs found
.loop:
  CPX BATCH_EXTRA
  BEQ .done                ; Taken as many as allowed
  JSR key_peek
  BCC .done                ; No key available, stop
  CMP LAST_KEY
  BNE .done                ; Not a pair start: leave it buffered
  INC HAS_KEY_DECODED      ; Consume the first key ($FF -> $00)
  JSR key_peek
  BCC .partial             ; No second key available
  CMP BUF_TEMP
  BNE .partial             ; Second key doesn't match: leave it buffered
  INC HAS_KEY_DECODED      ; Consume the second key
  ; Full pair matched
  INX
  BCS .loop                ; Always (C = 1 from the match)
.partial:
  ; Save consumed first key for restore after command completes
  LDA LAST_KEY
  STA BATCH_RESTORE_KEY
.done:
  STX BATCH_EXTRA
  RTS

; --- Common yank/delete operations ---

; Yank then delete N lines starting at FILE_LINE16
; Input: BUF_TEMP16 = count of lines (from get_count)
; Returns carry set = yank overflow, carry clear = success
; On success: lines deleted, FILE_LINE16 clamped, YANK_LINES16 set
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_LEN16
yank_delete_current_lines:
  JSR yank_current_lines
  BCS ydcl_done              ; C = 1: overflow
; Record undo, then delete BUF_TEMP16 lines at FILE_LINE16; returns C = 0
undo_delete_current_lines:
  JSR undo_record_line_delete
  JSR delete_current_lines
  CLC
ydcl_done:
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
  JMP clamp_file_line        ; Clamp file line if past end of file

; Count the newlines in the BUF_LEN16 bytes at the cursor
; Output: BUF_TEMP16 = the count, BUF_DST16 = the address after them,
; Y = 0.  Clobbers A, X, BUF_PTR16, BUF_SRC16
count_newlines:
  JSR get_cursor_buf_ptr     ; BUF_PTR16 = cursor position
  CP16 BUF_PTR16, BUF_DST16 ; BUF_DST16 = scan pointer
  CP16 BUF_LEN16, BUF_SRC16 ; BUF_SRC16 = bytes left to scan
  LDA #0
  STA_LH16 BUF_TEMP16
  TAY                        ; Y = 0 for the scan
.scan_nl:
  TST16 BUF_SRC16
  BEQ .scan_done
  LDA (BUF_DST16),Y
  CMP #'\n'
  BNE .scan_next
  INC16 BUF_TEMP16           ; Found newline
.scan_next:
  INC16 BUF_DST16
  DEC16 BUF_SRC16
  JMP .scan_nl
.scan_done:
  RTS

; Record undo, then delete chars at the cursor (once they are yanked)
; Input: BUF_LEN16 = number of bytes to delete, cursor position set via CURSOR_COL16
; Deletes, rebuilds lines, sets MODIFIED
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_TEMP16
undo_delete_at_cursor:
  JSR undo_record_char_delete
  ; Fall through to delete_at_cursor

; Delete bytes at cursor position (no yank)
; Input: BUF_LEN16 = number of bytes to delete, cursor position set via CURSOR_COL16
; Shifts buffer, adjusts line table (incremental if no newlines), sets MODIFIED
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_TEMP16
delete_at_cursor:
  JSR count_newlines         ; BUF_TEMP16 = the range's newlines
  ; Newlines found: BEFORE the shift, sum the old screen rows of the
  ; cursor line and the lines joined to it into DELETE_SCREEN_ROWS (0 if
  ; over 255; over 255 newlines walk 256 lines, so over 255 rows)
  LDA BUF_TEMP16
  LDX BUF_TEMP16 + 1
  BEQ .nl_count
  LDA #$FF
.nl_count:
  TAX
  BEQ .no_precompute
  JSR compute_delete_rows_join
.no_precompute:
  JSR get_cursor_buf_ptr     ; Recompute BUF_PTR16 (scan clobbered BUF_DST16)
  JSR buf_shift_left_16
  TST16 BUF_TEMP16
  BNE .full_rebuild
  ; Incremental: negate BUF_LEN16 into BUF_SRC16 (A = 0 here)
  SEC
  SBC BUF_LEN16
  STA BUF_SRC16
  LDA #0
  SBC BUF_LEN16 + 1
  STA BUF_SRC16 + 1
  JSR buf_adjust_lines_apply
  JMP set_modified
.full_rebuild:
  JSR buf_rebuild_lines
  ; Adjust marks for the deleted newlines (BUF_TEMP16 = count)
  LDAX16 FILE_LINE16
  JSR mark_adjust_join
  ; Signal line-delete scroll, skip cursor row in scroll region:
  ; SCROLL_DELTA = old total rows - the cursor line's new rows, or 0 (a
  ; full repaint) if the old total was over 255
  JSR file_line_rows
  LDX DELETE_SCREEN_ROWS     ; X = old total screen rows
  STA DELETE_SCREEN_ROWS     ; Cursor line screen rows (new)
  TXA
  BEQ .set_delta
  SEC
  SBC DELETE_SCREEN_ROWS
.set_delta:
  STA SCROLL_DELTA            ; pre-computed scroll displacement
  LDA #RF_CHAR_JOIN          ; Line-delete, skip cursor row, repaint cursor
  ; fall through

; Set RENDER_FLAG from A and mark the buffer modified.  Clobbers A
set_modified_render:
  STA RENDER_FLAG
; Mark the buffer modified.  Clobbers A; preserves X, Y and the carry
set_modified:
  LDA #$FF
  STA MODIFIED
  RTS

; Partial line repaint from the cursor: RENDER_FROM_COL16 = CURSOR_COL16,
; or from A columns before it (_before_cursor, A <= CURSOR_COL16).
; Clobbers A; preserves X, Y
set_render_from_cursor:
  LDA #0
set_render_from_before_cursor:
  EOR #$FF
  SEC
  ADC CURSOR_COL16           ; CURSOR_COL16 - A: + (255 - A) + 1
  STA RENDER_FROM_COL16
  LDA CURSOR_COL16 + 1
  ADC #$FF                   ; - 1 unless the low byte carried
  STA RENDER_FROM_COL16 + 1
char_op_ret:
  RTS

; --- Operator dispatch ---

OP_YANK   = 0
OP_DELETE = 1
OP_CHANGE = 2

; Apply operator to character range at cursor
; Input: A = operator (OP_YANK, OP_DELETE, OP_CHANGE)
;        BUF_LEN16 = byte count of range
;        Cursor at start of range (CURSOR_COL16, FILE_LINE16)
; Yanks the range first. If it does not fit the yank buffer, shows "Yank
; buffer full" and changes nothing else (the yank, the undo record and
; the mode included), as dd does.
; OP_YANK:   done
; OP_DELETE: record undo, delete, clamp cursor
; OP_CHANGE: record undo, delete, enter insert mode
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16
apply_char_operator:
  PHA                          ; Save operator
  JSR get_cursor_src           ; BUF_SRC16 = range start
  JSR yank_add_chars           ; Preserves BUF_LEN16
  PLA                          ; Restore operator (keeps C; Z = OP_YANK)
  BCS show_yank_overflow       ; Does not fit: nothing changes
  BEQ char_op_ret              ; Yank only: no delete, no MODIFIED
  PHA
  JSR undo_delete_at_cursor
  PLA
  CMP #OP_CHANGE
  BEQ .change
  ; OP_DELETE: clamp cursor
  JMP clamp_cursor_col
.change:
  JMP enter_insert_mode

; Show yank overflow error: show message, clear count
; Used when a yank did not fit (the yank buffer is unchanged)
show_yank_overflow:
  JSR range_yank_full        ; "Yank buffer full"
  JMP clear_count

; --- Shared batched character delete (for x and X commands) ---

; BUF_LEN16 = the chars from the cursor to the end of its line,
; LINE_LEN16 - CURSOR_COL16 (Z set: fewer than 256).  Clobbers A
chars_left:
  SEC
  SBC16 LINE_LEN16, CURSOR_COL16, BUF_LEN16
  RTS

; Compute forward character range from cursor
; Input: X = char count (8-bit), LINE_LEN16 = line length (from check_cursor_in_line)
; Output: BUF_LEN16 = min(X, available chars on line), carry set if nothing
; Clobbers: A
compute_char_range_forward:
  JSR chars_left             ; BUF_LEN16 = available
  BNE .use_x                 ; Available >= 256 > X
  CPX BUF_LEN16
  BCS .done                  ; X >= available: keep available
.use_x:
  STX BUF_LEN16
  LDA #0
  STA BUF_LEN16 + 1
.done:
  JMP range_epilogue

; Batched character delete for x (batched_char_delete) and X
; (batched_char_delete_back, cursor already moved to the range start).
; When batched, the register gets what the last key press deleted: the
; range's last char for x, its first char for X.  Batched x presses left
; over at the line end go on as X from the line end.
; Input: X = total count, BATCH_EXTRA = # of extra batched units (0 = no batching)
;        BUF_DELTA = count (x: from get_batched_count)
;        LINE_LEN16 = line length (from check_cursor_in_line)
; Clobbers: A, X, Y, BUF_PTR16, BUF_SRC16, BUF_DST16, BUF_LEN16
batched_char_delete_back:
  LDY #$FF                  ; Y = DEL_BACK flag (kept until .batched)
  BNE bcd_start             ; Always taken

; x on an empty line: an empty change, as in vim
x_empty:
  JSR undo_record_empty
  BEQ bcd_done               ; Always

; x and Del: delete count chars at the cursor, with the typed-ahead x's
normal_delete_char:
  JSR check_cursor_in_line
  BCS x_empty
  JSR get_batched_count      ; X = total, BATCH_EXTRA = extras
batched_char_delete:
  LDY #0
bcd_start:
  JSR set_render_from_cursor    ; Repaint from the range start (keeps X, Y)
  JSR compute_char_range_forward
  BCS bcd_done
  JSR set_shift_delete
  LDA BATCH_EXTRA
  BNE .batched
  ; --- Non-batched: yank+delete the full range (at most 255 chars, so
  ; it always fits the yank buffer), clamp the cursor ---
.unbatched:
  LDA #OP_DELETE
  JSR apply_char_operator
  JMP clear_count

.x_past_end:
  LDA BUF_DELTA              ; The count (get_batched_count)
  CMP BUF_LEN16              ; C = 1: it reaches the line end
  LDA CURSOR_COL16
  ORA CURSOR_COL16 + 1
  BNE .leftward
  ; From column 0 the presses only delete forward (to the line end, and
  ; past it they do nothing): the forward range stands, and when the
  ; count alone empties the line, its delete is the last
  BCC .yank_last
  BCS .unbatched
.leftward:
  ; One at a time, x on the last char leaves the cursor on the new last
  ; char, which the next x deletes: min(count, the range) + the extras
  ; is X of as many from the line end
  LDA BUF_DELTA
  BCC .count_ok
  LDA BUF_LEN16              ; The count stops at the line end
.count_ok:
  CLC
  ADC BATCH_EXTRA
  TAX                        ; X = the chars to delete (< 256)
  STY BUF_DELTA              ; (Y = 0) No X count of its own
  CP16 LINE_LEN16, CURSOR_COL16
  JMP delete_char_back_x

.batched:
  ; x presses left over at the line end (the range stopped short of X:
  ; only x's range can) delete leftward from there, as one at a time
  CPX BUF_LEN16
  BNE .x_past_end
.yank_last:
  ; --- Batched: yank only what the last key press deleted (the range's
  ; last char for x, its first char for X), then delete the full range ---
  PUSH16 BUF_LEN16              ; Save full range
  TYA
  PHA                           ; Save the DEL_BACK flag
  JSR get_cursor_src            ; BUF_SRC16 = range start
  PLA
  BNE .yank_one                 ; X: the first char
  LDX BUF_LEN16                 ; x: the last char (range <= 255)
  DEX
  TXA
  ADDA16 BUF_SRC16
.yank_one:
  LDA #1
  STA BUF_LEN16
  LDA #0
  STA BUF_LEN16 + 1
  JSR yank_add_chars            ; (resets the yank buffer)
  POP16 BUF_LEN16               ; Restore full range
  ; Record undo, delete full range in single operation
  JSR undo_delete_at_cursor
  JSR clamp_cursor_col
bcd_done:
  JMP clear_count

; ICH/DCH hint for deleting BUF_LEN16 (<= 255) chars at the cursor.
; Over 128 chars -n does not fit SHIFT_NET's signed byte: no hint (the
; line is rewritten)
; Clobbers: A
set_shift_delete:
  LDA #0
  SEC
  SBC BUF_LEN16
  BPL .done                  ; -n does not fit
  STA SHIFT_NET
  LDA #0
  STA SHIFT_WRITE
.done:
  RTS
