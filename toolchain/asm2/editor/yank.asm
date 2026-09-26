; Yank (copy) buffer for cut/copy/paste operations
;
; The yank buffer holds the last yanked or deleted text for paste: whole
; lines (YANK_LINE, newline-terminated like the text buffer) or characters
; (YANK_CHAR). Every yank replaces its contents.
;
; Memory layout:
;   YANK_BUF  ($E000) - Start of yank buffer
;   YANK_LIMIT ($F000) - End of yank buffer (4KB)

YANK_BUF   = $E000
YANK_LIMIT = $F000

YANK_LINE = 0
YANK_CHAR = 1

  .zeropage

YANK_END16:    .word     ; Points one past last byte in yank buffer
YANK_LINES16:  .word     ; 16-bit line count for yank buffer
YANK_SIZE16:   .word     ; Single yank size for paste operations
YANK_TYPE:     .byte     ; 0=line, 1=char

  .code

; Initialize yank buffer (call once at startup)
yank_init:
; Clear yank buffer (reset to empty)
yank_clear:
  SET16 YANK_BUF, YANK_END16
  LDA #YANK_LINE
  STA YANK_TYPE
  RTS

; Replace the yank buffer with N contiguous lines (YANK_TYPE = YANK_LINE)
; Input: A/X = first line number (low/high), BUF_TEMP16 = count of lines (16-bit)
; Clamps count to available lines. Uses mem_copy_down for page-optimized copy.
; Returns carry set = yank buffer full (it is left empty), carry clear = success
; On success: YANK_END16 updated, YANK_LINES16 = BUF_TEMP16 = actual lines copied
yank_add_lines:
  STAX16 BUF_SRC16           ; BUF_SRC16 = first line number
  JSR yank_clear             ; Empty line yank (stays empty if too big)

  ; Clamp count: BUF_TEMP16 = min(count, LINE_COUNT16 - first_line)
  SEC
  LDA LINE_COUNT16
  SBC BUF_SRC16
  TAY
  LDA LINE_COUNT16 + 1
  SBC BUF_SRC16 + 1
  TAX                        ; Y/X = available lines (low/high)
  CPY BUF_TEMP16
  SBC BUF_TEMP16 + 1
  BCS .count_ok              ; available >= count: keep count
  STY BUF_TEMP16
  STX BUF_TEMP16 + 1
.count_ok:

  LDAX16 BUF_SRC16
  JSR buf_line_span          ; BUF_SRC16 = start, BUF_LEN16 = size
  JSR yank_store
  BCS .ret                   ; Yank buffer full
  CP16 BUF_TEMP16, YANK_LINES16  ; Carry stays clear
.ret:
  RTS

; Replace the yank buffer with character data
; Input: BUF_SRC16 = source address, BUF_LEN16 = byte count
; Returns carry set = buffer full (yank buffer unchanged), carry clear =
; success (YANK_TYPE = YANK_CHAR)
yank_add_chars:
  JSR yank_store
  BCS .ret
  LDA #YANK_CHAR
  STA YANK_TYPE              ; Carry stays clear
.ret:
  RTS

; Replace the yank buffer contents with the BUF_LEN16 bytes at BUF_SRC16
; (YANK_TYPE is left to the caller)
; Returns carry set if they do not fit (nothing changed), carry clear on
; success. Sets BUF_PTR16 = BUF_SRC16 + BUF_LEN16, preserves BUF_LEN16.
; Clobbers A, Y, BUF_SRC16, BUF_DST16
yank_store:
  ; Fits iff YANK_BUF + size <= YANK_LIMIT (full iff end >= LIMIT+1)
  CLC
  ADCI16 BUF_LEN16, YANK_BUF, BUF_DST16
  LDA BUF_DST16
  CMP #<YANK_LIMIT+$01
  LDA BUF_DST16 + 1
  SBC #>YANK_LIMIT+$01
  BCS .ret
  CP16 BUF_DST16, YANK_END16 ; New end of the yank buffer

  ; mem_copy_down(BUF_SRC16, BUF_SRC16 + size, YANK_BUF)
  ADC16 BUF_SRC16, BUF_LEN16, BUF_PTR16  ; Carry clear from the check
  SET16 YANK_BUF, BUF_DST16
  JSR mem_copy_down
  CLC
.ret:
  RTS

; Compute yank buffer size in BUF_LEN16
; Returns carry set if yank buffer empty, carry clear if has content
yank_get_size:
  LDA YANK_END16             ; YANK_BUF is page-aligned
  STA BUF_LEN16
  SEC
  LDA YANK_END16 + 1
  SBC #>YANK_BUF
  STA BUF_LEN16 + 1
  ; Check if size is zero
  ORA BUF_LEN16
  BEQ .empty
  CLC
  RTS
.empty:
  SEC
  RTS

; Paste yank buffer below current line, N times in one batch operation
; Input: BUF_TEMP16 = count of times to paste (16-bit)
; Returns carry set = error (empty/full), carry clear = success
yank_paste_below_n:
  JSR yank_paste_setup
  BCS yank_paste_ret          ; Empty yank

  ; Find insertion point: after current line's newline
  JSR get_current_line_ptr    ; BUF_PTR16 = start of current line
  JSR advance_past_line_end   ; BUF_PTR16 = insertion point (after newline)

  JSR yank_paste_core
  BCS yank_paste_ret

  ; Move cursor to first pasted line
  INC16 FILE_LINE16
  BCC yank_paste_finish       ; Always taken (BCS above not taken;
                              ; INC16 = INC/BNE/INC touches no carry)

; Paste yank buffer above current line, N times in one batch operation
; Input: BUF_TEMP16 = count of times to paste (16-bit)
; Returns carry set = error (empty/full), carry clear = success
yank_paste_above_n:
  JSR yank_paste_setup
  BCS yank_paste_ret          ; Empty yank

  ; Insertion point: start of current line
  JSR get_current_line_ptr    ; BUF_PTR16 = start of current line

  JSR yank_paste_core
  BCS yank_paste_ret

  ; Cursor stays at same line number
  ; fall through

; Shared paste tail: cursor to col 0 (clamped), carry clear = success
yank_paste_finish:
  LDA #0
  STA_LH16 CURSOR_COL16
  JSR clamp_cursor_col
  CLC
yank_paste_ret:
  RTS

; Compute yank size and total paste size
; Input: BUF_TEMP16 = paste count (16-bit, >= 1, preserved)
; Output: BUF_LEN16 = total size, YANK_SIZE16 = single size
; Returns carry set if yank buffer empty, carry clear if ready
; Clobbers A, X, COUNT16, DIV_INPUT16
yank_paste_setup:
  JSR yank_get_size           ; BUF_LEN16 = single yank size
  BCS yank_paste_ret          ; Empty yank (carry set)
  CP16 BUF_LEN16, YANK_SIZE16 ; YANK_SIZE16 = single size
  LDX #YANK_SIZE16
  JSR mul_by_count            ; BUF_LEN16 = YANK_SIZE16 * BUF_TEMP16
  CLC
  RTS

; BUF_LEN16 = (16-bit zero-page value at X) * BUF_TEMP16, low 16 bits
; (shift and add: one pass per bit of the count).
; Clobbers A, COUNT16, DIV_INPUT16
mul_by_count:
  CP16 BUF_TEMP16, COUNT16    ; Multiplier, shifted right
  LDA $00,X
  STA DIV_INPUT16             ; Multiplicand, shifted left
  LDA $01,X
  STA DIV_INPUT16 + 1
  LDA #0
  STA_LH16 BUF_LEN16
.bit:
  LSR16 COUNT16
  BCC .next
  CLC
  ADC16 BUF_LEN16, DIV_INPUT16, BUF_LEN16
.next:
  ASL16 DIV_INPUT16
  TST16 COUNT16
  BNE .bit
  RTS

; Show "Buffer full" and return carry set (a paste that did not fit)
paste_full:
  JSR show_buffer_full_msg
  SEC
  RTS

; Shift right, copy yank buffer N times into gap, rebuild lines
; Input: BUF_PTR16 = insertion point, BUF_LEN16 = total size, BUF_TEMP16 = count (16-bit)
; Returns carry set = buffer full, carry clear = success
yank_paste_core:
  ; Shift right to make room
  JSR buf_shift_right_16
  BCS paste_full

  ; Copy yank buffer into gap N times using mem_copy_down
  ; BUF_PTR16 = insertion point (gap start)
.copy_loop:
  ; Check if count is zero
  TST16 BUF_TEMP16
  BEQ .done

  ; Set up mem_copy_down: src=YANK_BUF, end=YANK_END16, dst=write_pos
  PUSH16 BUF_PTR16            ; Save write position
  CP16 BUF_PTR16, BUF_DST16   ; BUF_DST16 = write position
  SET16 YANK_BUF, BUF_SRC16
  CP16 YANK_END16, BUF_PTR16  ; BUF_PTR16 = end of yank data
  JSR mem_copy_down            ; Preserves BUF_PTR16
  POP16 BUF_PTR16             ; Restore write position

  ; Advance write position by single size
  CLC
  ADC16 BUF_PTR16, YANK_SIZE16, BUF_PTR16

  ; Decrement count and loop
  DEC16 BUF_TEMP16
  JMP .copy_loop

.done:
  ; Rebuild lines once
  JSR buf_rebuild_lines
  CLC
  RTS

; Adjust marks after a line paste: UNDO_PASTE_COUNT16 copies of the yank
; (every caller has recorded the paste count there) now start at FILE_LINE16
; Output: BUF_TEMP16 = total pasted lines.  Sets MODIFIED.
; Clobbers A, X, Y, BUF_LEN16, COUNT16, DIV_INPUT16
paste_adjust_marks:
  JSR undo_compute_paste_lines  ; BUF_TEMP16 = YANK_LINES16 * count
  LDAX16 FILE_LINE16
  JSR mark_adjust_insert
  JMP set_modified

; Check if yank buffer contains a newline character
; Input: yank buffer contents and YANK_END16 must be stable (not mid-mutation)
; Output: carry set if newline found, carry clear if not
; Clobbers: A, Y, BUF_SRC16
yank_has_newline:
  SET16 YANK_BUF, BUF_SRC16
  LDY #0
.loop:
  CMP16 BUF_SRC16, YANK_END16
  BEQ .not_found
  LDA (BUF_SRC16),Y
  CMP #'\n'
  BEQ .found
  INC16 BUF_SRC16
  JMP .loop
.not_found:
  CLC
  RTS
.found:
  SEC
  RTS
