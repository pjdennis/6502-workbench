; Yank (copy) buffer for cut/copy/paste operations
;
; The yank buffer holds the last yanked or deleted text for paste: whole
; lines (YANK_LINE, newline-terminated like the text buffer) or characters
; (YANK_CHAR). Every yank replaces its contents.
;
; Memory layout (YANK_BUF, YANK_LIMIT: the memory map in editor.asm):
;   YANK_BUF   - Start of yank buffer (page-aligned)
;   YANK_LIMIT - End of yank buffer

YANK_LINE = 0
YANK_CHAR = 1

; (zero-page variables: zp.asm)

; Initialize yank buffer (call once at startup)
yank_init:
; Clear yank buffer (reset to empty)
yank_clear:
  SET16 YANK_BUF, YANK_END16
  LDA #YANK_LINE
  STA YANK_TYPE
  RTS

; Replace the yank buffer with the lines from FILE_LINE16, as below
yank_current_lines:
  LDAX16 FILE_LINE16
  ; fall through

; Replace the yank buffer with N contiguous lines (YANK_TYPE = YANK_LINE)
; Input: A/X = first line number (low/high), BUF_TEMP16 = count of lines (16-bit)
; Clamps count to available lines. Uses mem_copy_down for page-optimized copy.
; Returns carry set = yank buffer full (yank buffer unchanged), carry clear =
; success
; On success: YANK_END16 updated, YANK_LINES16 = BUF_TEMP16 = actual lines copied
yank_add_lines:
  STAX16 BUF_SRC16           ; BUF_SRC16 = first line number

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
  LDY #YANK_LINE
  JSR yank_store
  BCS .ret                   ; Yank buffer full
  CP16 BUF_TEMP16, YANK_LINES16  ; Carry stays clear
.ret:
  RTS

; Replace the yank buffer with character data (YANK_TYPE = YANK_CHAR)
; Input: BUF_SRC16 = source address, BUF_LEN16 = byte count
; Returns carry set = buffer full (yank buffer unchanged), carry clear =
; success
yank_add_chars:
  LDY #YANK_CHAR
  ; fall through

; Replace the yank buffer with the BUF_LEN16 bytes at BUF_SRC16, of type Y
; Returns carry set if they do not fit (nothing changed), carry clear on
; success. Sets BUF_PTR16 = BUF_SRC16 + BUF_LEN16, preserves BUF_LEN16.
; Their newlines are not counted yet (YANK_LINES16 high byte $FF: a line
; yank sets its count, a char paste counts them, yank_count_newlines).
; A new yank also ends an undo that reads the yank buffer (the types
; below UNDO_JOIN): u would replay it. A delete records its undo after
; its yank.
; Clobbers A, Y, BUF_SRC16, BUF_DST16
yank_store:
  ; Fits iff size <= YANK_LIMIT - YANK_BUF (compare the size itself:
  ; YANK_BUF + size wraps past $FFFF for sizes of 8 KB and more)
  LDA BUF_LEN16
  CMP #<YANK_LIMIT-YANK_BUF+$01
  LDA BUF_LEN16 + 1
  SBC #>YANK_LIMIT-YANK_BUF+$01
  BCS .ret
  STY YANK_TYPE
  LDA #$FF
  STA YANK_LINES16 + 1       ; Not counted yet
  ; New end of the yank buffer (carry clear from the check; the sum is at
  ; most YANK_LIMIT, so it stays clear)
  ADCI16 BUF_LEN16, YANK_BUF, YANK_END16

  ; mem_copy_down(BUF_SRC16, BUF_SRC16 + size, YANK_BUF)
  ADC16 BUF_SRC16, BUF_LEN16, BUF_PTR16
  SET16 YANK_BUF, BUF_DST16
  JSR mem_copy_down
  LDA UNDO_TYPE
  CMP #UNDO_JOIN
  BCS .keep_undo             ; The undo keeps its own data
  JSR undo_clear
.keep_undo:
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
  BCS yank_paste_ret          ; Empty yank, or no room for its lines

  ; Insertion point: the start of the next line (the end of the text
  ; after the last line)
  JSR get_next_line_ptr

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
  BCS yank_paste_ret          ; Empty yank, or no room for its lines

  ; Insertion point: start of current line
  JSR get_current_line_ptr    ; BUF_PTR16 = start of current line

  JSR yank_paste_core
  BCS yank_paste_ret

  ; Cursor stays at same line number
  ; fall through

; Shared paste tail: the cursor to the first non-blank of the (first)
; line put in, as vim, carry clear = success
yank_paste_finish:
  JSR first_nonblank
  CLC
yank_paste_ret:
  RTS

; Check that the line table has room for a paste's new lines (YANK_LINES16
; per copy), then compute yank size and total paste size
; Input: BUF_TEMP16 = paste count (16-bit, >= 1, preserved)
; Output: BUF_LEN16 = total size ($FFFF if it passes 16 bits, which no
;         buffer shift allows), YANK_SIZE16 = single size
; Returns carry set if the lines do not fit ("Buffer full") or the yank
; buffer is empty, carry clear if ready
; Clobbers A, X, Y, COUNT16, DIV_INPUT16
yank_paste_setup:
  LDX #YANK_LINES16
  JSR mul_by_count            ; A/X = new lines ($FFFF past 16 bits)
  JSR check_line_room
  BCS paste_full
; Same without the line check (undo of a paste, which deletes it)
yank_paste_size:
  JSR yank_get_size           ; BUF_LEN16 = single yank size
  BCS yank_paste_ret          ; Empty yank (carry set)
  CP16 BUF_LEN16, YANK_SIZE16 ; YANK_SIZE16 = single size
  LDX #YANK_SIZE16
  JSR mul_by_count            ; BUF_LEN16 = YANK_SIZE16 * BUF_TEMP16
  CLC
  RTS

; BUF_LEN16 = A/X (low/high) = (16-bit zero-page value at X) *
; BUF_TEMP16, or $FFFF if that passes 16 bits (shift and add: one pass
; per bit of the count).  Clobbers COUNT16, DIV_INPUT16
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
  BCS .overflow
.next:
  ASL16 DIV_INPUT16           ; C = 1: the multiplicand passed 16 bits
  TST16 COUNT16
  BEQ .done                   ; No count bits left
  BCC .bit
.overflow:                    ; The product passes 16 bits
  LDA #$FF
  STA_LH16 BUF_LEN16
.done:
  LDAX16 BUF_LEN16
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
  JSR yank_copy_n             ; Fill the gap
  ; Rebuild lines once
  JSR buf_rebuild_lines
  CLC
  RTS

; Copy the yank buffer BUF_TEMP16 (16-bit) times to BUF_PTR16 using
; mem_copy_down, advancing BUF_PTR16 by YANK_SIZE16 per copy
; (YANK_SIZE16 = YANK_END16 - YANK_BUF).  Exits with BUF_TEMP16 = 0.
; Preserves X.  Clobbers A, Y, BUF_SRC16, BUF_DST16
yank_copy_n:
  ; Check if count is zero
  TST16 BUF_TEMP16
  BEQ .done

  ; Set up mem_copy_down: src=YANK_BUF, end=YANK_END16, dst=write_pos
  PUSH16 BUF_PTR16            ; Save write position
  JSR ptr_to_dst              ; BUF_DST16 = write position
  SET16 YANK_BUF, BUF_SRC16
  CP16 YANK_END16, BUF_PTR16  ; BUF_PTR16 = end of yank data
  JSR mem_copy_down            ; Preserves BUF_PTR16
  POP16 BUF_PTR16             ; Restore write position

  ; Advance write position by single size
  CLC
  ADC16 BUF_PTR16, YANK_SIZE16, BUF_PTR16

  ; Decrement count and loop
  DEC16 BUF_TEMP16
  JMP yank_copy_n

.done:
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

; Count the newlines in the yank buffer into YANK_LINES16, the lines each
; copy of a paste adds (a char paste counts them first; a line yank's
; line count is its newline count already), unless they have been
; counted since the last yank: only then is its high byte $FF
; Output: carry set if there are any
; Clobbers: A, Y, BUF_SRC16
yank_count_newlines:
  LDA YANK_LINES16 + 1
  BPL .done                  ; Counted already
  LDY #0
  STY YANK_LINES16
  STY YANK_LINES16 + 1
  STY BUF_SRC16              ; YANK_BUF is page-aligned
  LDA #>YANK_BUF
  STA BUF_SRC16 + 1
.loop:
  CPY YANK_END16             ; Fast: compare low bytes
  BNE .byte
  LDA BUF_SRC16 + 1          ; Only when low bytes match
  CMP YANK_END16 + 1
  BEQ .done
.byte:
  LDA (BUF_SRC16),Y
  CMP #'\n'
  BNE .next
  INC16 YANK_LINES16
.next:
  INY
  BNE .loop                  ; Stay on the same page
  INC BUF_SRC16 + 1
  BNE .loop                  ; Always (the yank buffer ends before $FFFF)
.done:
  LDA YANK_LINES16
  ORA YANK_LINES16 + 1
  CMP #1                     ; C = any newlines
  RTS
