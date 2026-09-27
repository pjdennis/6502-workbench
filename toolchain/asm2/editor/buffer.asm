; Text buffer data structure and operations
;
; Memory layout:
;   TEXT_BUF           - Start of text buffer (page-aligned, past end of code)
;   LINE_TBL ($D800)   - Line pointer table (16-bit pointers, room for 1024)
;
; The text buffer stores all text contiguously. Lines are delimited by $0A.
; The line table stores 16-bit pointers to the start of each line.
; Insertions/deletions shift all text after the edit point.
;
; TEXT_BUF and TEXT_LIMIT are defined at the end of editor.asm as floating
; labels, so TEXT_BUF automatically adjusts as the code grows.

LINE_TBL    = $D800  ; Line pointer table (2 bytes per entry)
MAX_LINES   = $03FF  ; Most lines a buffer holds (1023: LINE_TBL has room
                     ; for 1024 entries, and one stays free)
BATCH_BUF   = $D600  ; Staging buffer for batch insert (32 bytes)
BATCH_MAX   = 32     ; Maximum batch size

; (zero-page variables: zp.asm)

; Initialize empty buffer
; Sets up an empty buffer with one empty line
buf_init:
  SET16 TEXT_BUF, BUF_END16
  ; Empty buffer: appends a newline for one empty line, builds line table
  JMP buf_ensure_nonempty_rebuild

; Load file into buffer
; File handle in A (already opened)
; On return: buffer contains file contents, line table built
; Sets READONLY (clear on entry) if the file was truncated: it filled the
; text buffer or, in buf_rebuild_lines, the line table
buf_load_file:
  STA FILE_HANDLE
  LDA #0
  STA BUF_END16           ; BUF_END16 = TEXT_BUF (page-aligned)
  TAY                     ; Y = page offset, set once
  LDA #>TEXT_BUF
  STA BUF_END16 + 1
.read_loop:
  LDA FILE_HANDLE
  JSR read                ; preserves X, Y
  BCS .read_done
  STA (BUF_END16),Y
  INY
  BNE .read_loop          ; Stay on same page
  ; Page boundary (every 256 chars)
  INC BUF_END16 + 1
  LDA BUF_END16 + 1
  CMP #>TEXT_LIMIT
  BCC .read_loop
  ; Buffer full - the file was truncated if there is more to read
  LDA FILE_HANDLE
  JSR read
  BCS .read_done
  DEC READONLY            ; $00 -> $FF
.read_done:
  STY BUF_END16           ; Reconstruct full pointer
  ; Ensure buffer ends with newline
  SEC
  SBCI16 BUF_END16, $0001, BUF_PTR16

  ; Check if last byte is newline
  LDY #0
  LDA #'\n'
  CMP (BUF_PTR16),Y
  BEQ .has_newline
  ; Need to add a newline: append it if there is room
  LDX BUF_END16 + 1          ; BUF_END16 is at the limit only as limit:00
  CPX #>TEXT_LIMIT
  BCC .append
  ; Full - overwrite the last byte instead, so the file is truncated
  STA (BUF_PTR16),Y
  DEC READONLY               ; Nonzero: read-only
  BNE .has_newline           ; Always ($FF, or $FE if already truncated)
.append:
  JSR buf_append_nl
.has_newline:

  ; If buffer is empty (nothing read), add a newline for one empty line
  JMP buf_ensure_nonempty_rebuild

; Save buffer to file
; File handle in A (already opened for write)
; Writes every byte from TEXT_BUF to BUF_END16, including the final
; newline (so an empty buffer, one empty line, saves as a single newline)
buf_save_file:
  STA FILE_HANDLE
  LDY #0                  ; Y = page offset, set once
  STY BUF_PTR16           ; BUF_PTR16 = TEXT_BUF (page-aligned)
  LDA #>TEXT_BUF
  STA BUF_PTR16 + 1
.write_loop:
  CPY BUF_END16           ; Fast: compare low bytes
  BNE .do_write
  LDA BUF_PTR16 + 1       ; Only when low bytes match
  CMP BUF_END16 + 1
  BEQ .write_done
.do_write:
  LDA (BUF_PTR16),Y
  LDX FILE_HANDLE
  JSR write               ; preserves Y
  INY
  BNE .write_loop         ; Stay on same page
  ; Page boundary
  INC BUF_PTR16 + 1
  BNE .write_loop            ; Always (the buffer never reaches page 0)
.write_done:
  RTS

; Get pointer to start of line N (N in A/X, low/high)
; Returns pointer in BUF_PTR16
; Clobbers A, Y
buf_get_line_ptr:
  ; Entry address = LINE_TBL + N * 2 (LINE_TBL is page-aligned and
  ; N < $8000, so the ROL leaves C = 0 for the high-byte add)
  STA BUF_PTR16
  TXA
  ASL BUF_PTR16
  ROL
  ADC #>LINE_TBL
  STA BUF_PTR16 + 1
  ; Read the 16-bit pointer from the table
  LDY #0
  LDA (BUF_PTR16),Y
  PHA
  INY
  LDA (BUF_PTR16),Y
  STA BUF_PTR16 + 1
  PLA
  STA BUF_PTR16
  RTS

; Get length of line N (N in A/X, low/high)
; Returns 16-bit length in A (low) / X (high), not counting the newline
; Leaves (BUF_PTR16),Y at the newline (BUF_PTR16 = line start + X pages)
buf_get_line_len:
  JSR buf_get_line_ptr
  JSR find_line_end
  TYA                        ; A = low byte of length
  RTS

; Scan (BUF_PTR16) for newline character
; Input: BUF_PTR16 = scan start
; Output: (BUF_PTR16),Y points to '\n', X = page crosses
; Clobbers: A
find_line_end:
  LDX #0
  LDY #0
.loop:
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .done
  INY
  BNE .loop
  INC BUF_PTR16 + 1
  INX
  BNE .loop                  ; Always (X counts pages, never wraps)
.done:
  RTS

; Scan (BUF_PTR16) for newline, then advance BUF_PTR16 past it
; Input: BUF_PTR16 = scan start
; Output: BUF_PTR16 = address after the newline
; Clobbers: A, X, Y
advance_past_line_end:
  JSR find_line_end
  TYA
  SEC                        ; + 1: step past the newline
  BCS ptr_adc_a              ; Always taken

; BUF_PTR16 += A (ptr_adc_a: += A + carry).  Clobbers A; preserves X, Y
ptr_add_a:
  CLC
ptr_adc_a:
  ADC BUF_PTR16
  STA BUF_PTR16
  BCC .done
  INC BUF_PTR16 + 1
.done:
  RTS

; Open a blank line: insert a newline at BUF_PTR16, rebuild the line
; table and move the marks at/after line A/X (the new line) down one.
; Returns carry set = the text buffer or the line table is full (nothing
; changed), clear = success
; Clobbers A, X, Y
buf_open_line:
  PHA
  TXA
  PHA                        ; Save the new line's number
  LDA #1
  STA BUF_LEN16
  LDX #0
  STX BUF_LEN16 + 1
  JSR check_line_room        ; A/X = 1 more line
  BCS .full
  JSR buf_shift_right_16
  BCS .full
  LDA #'\n'
  LDY #0
  STA (BUF_PTR16),Y
  JSR buf_rebuild_lines
  PLA
  TAX
  PLA
  JSR mark_insert_one
  CLC                        ; Success (mark_insert_one leaves carry set)
  RTS
.full:
  PLA
  PLA                        ; (PLA keeps the carry set)
  RTS

; Returns carry set if A/X (low/high) more lines do not fit the line
; table (LINE_COUNT16 + A/X > MAX_LINES).  Every edit that adds lines
; checks this before changing anything.  Clobbers A, Y
check_line_room:
  CLC
  ADC LINE_COUNT16
  TAY
  TXA
  ADC LINE_COUNT16 + 1
  BCS .done                  ; The total passes $FFFF
  CPY #<MAX_LINES+$01
  SBC #>MAX_LINES+$01        ; C = the total passes MAX_LINES
.done:
  RTS

; Shift buffer right by BUF_LEN16 bytes at BUF_PTR16 (16-bit version)
; Input: BUF_PTR16 = insert point, BUF_LEN16 = shift amount (16-bit)
; Returns carry set = buffer full, carry clear = success
; Updates BUF_END16 on success. Does not modify BUF_PTR16.
; Clobbers A, Y, BUF_SRC16, BUF_DST16
buf_shift_right_16:
  ; Check if buffer has room for BUF_LEN16 bytes
  CLC
  LDA BUF_END16
  ADC BUF_LEN16
  STA BUF_DST16              ; Temp: new end low
  LDA BUF_END16 + 1
  ADC BUF_LEN16 + 1
  BCS .full             ; The new end passes $FFFF
  CMP #>TEXT_LIMIT
  BCC .has_room
  BNE .full
  LDA BUF_DST16
  BEQ .has_room         ; Exactly at limit is ok
.full:                  ; C = 1 from the ADC or the CMP
  RTS
.has_room:

  ; Check if nothing to move (insert at end; equality-only test)
  JSR cmp_ptr_end
  BEQ .shift_done

  ; Copy [BUF_PTR16, BUF_END16) up by BUF_LEN16, last byte first.
  ; BUF_SRC16/BUF_DST16 = page-aligned source/destination bases,
  ; Y = low byte of the byte being copied
  SEC
  LDA BUF_END16
  SBC #1
  TAY                        ; Y = low byte of last source byte
  LDA BUF_END16 + 1
  SBC #0
  STA BUF_SRC16 + 1          ; page of last source byte
  CLC
  ADC BUF_LEN16 + 1
  STA BUF_DST16 + 1
  LDA BUF_LEN16
  STA BUF_DST16              ; (BUF_DST16),Y = (BUF_SRC16),Y + BUF_LEN16
  LDA #0
  STA BUF_SRC16
  LDA BUF_SRC16 + 1
  CMP BUF_PTR16 + 1
  BEQ .last_page
  TYA
  BEQ .byte0                 ; First page holds only byte 0
.full_page:                  ; Copy Y..1 of this page, then byte 0
  LDA (BUF_SRC16),Y
  STA (BUF_DST16),Y
  DEY
  BNE .full_page
.byte0:
  LDA (BUF_SRC16),Y
  STA (BUF_DST16),Y
  DEY                        ; Y = $FF for the previous page
  DEC BUF_SRC16 + 1
  DEC BUF_DST16 + 1
  LDA BUF_SRC16 + 1
  CMP BUF_PTR16 + 1
  BNE .full_page
.last_page:                  ; Insert point's page: copy Y down to it
  LDA (BUF_SRC16),Y
  STA (BUF_DST16),Y
  CPY BUF_PTR16
  BEQ .shift_done
  DEY
  BCS .last_page             ; Always (Y > insert point low byte)

.shift_done:
  ; Update buffer end: add BUF_LEN16
  CLC
  ADC16 BUF_END16, BUF_LEN16, BUF_END16

  CLC              ; Success
  RTS

; Byte span of BUF_TEMP16 contiguous lines starting at line A/X
; The span ends at the start of the line after it, or at BUF_END16 when
; it reaches past the last line.
; Output: BUF_SRC16 = start, BUF_PTR16 = end, BUF_LEN16 = size in bytes
; Clobbers A, X, Y, BUF_DST16
buf_line_span:
  STA BUF_DST16              ; First line low byte (X = high byte)
  JSR buf_get_line_ptr       ; Preserves X
  CP16 BUF_PTR16, BUF_SRC16  ; BUF_SRC16 = start of the first line
  CP16 BUF_END16, BUF_PTR16  ; End = buffer end, unless a line follows
  ; Y/X = line after the span = first line + count; C = it is past the end
  CLC
  LDA BUF_DST16
  ADC BUF_TEMP16
  TAY
  TXA
  ADC BUF_TEMP16 + 1
  TAX
  CPY LINE_COUNT16
  SBC LINE_COUNT16 + 1
  BCS .have_end
  TYA
  JSR buf_get_line_ptr       ; BUF_PTR16 = start of the line after the span
.have_end:
  SEC
  SBC16 BUF_PTR16, BUF_SRC16, BUF_LEN16
  RTS

; Replace N contiguous lines starting at line A/X with one empty line
; (cc/S): as buf_delete_lines, but it keeps the last line's newline, so
; it never empties the buffer.  Same input as buf_delete_lines
buf_clear_lines:
  JSR buf_line_span
  DEC16 BUF_LEN16            ; Keep the last newline (the span ends in one)
  BCS buf_delete_span        ; Always (buf_line_span leaves C = 1)

; Delete N contiguous lines starting at line A/X
; Input: A/X = first line number (low/high), BUF_TEMP16 = count of lines to delete (16-bit)
; Handles end-of-file clamping, empty buffer, rebuilds line table once
buf_delete_lines:
  JSR buf_line_span
buf_delete_span:
  CP16 BUF_SRC16, BUF_PTR16  ; Delete point = start of the span
  JSR buf_shift_left_16
  ; If buffer is now empty, add a newline; rebuild line table
  JMP buf_ensure_nonempty_rebuild

; Shift buffer left by BUF_LEN16 bytes at BUF_PTR16 (16-bit version)
; Input: BUF_PTR16 = delete point, BUF_LEN16 = shift amount (16-bit)
; Updates BUF_END16. Leaves BUF_PTR16 = the old BUF_END16.
; Clobbers A, Y, BUF_SRC16, BUF_DST16
buf_shift_left_16:
  ; mem_copy_down(src = delete point + BUF_LEN16, end = BUF_END16,
  ; dst = delete point); it copies nothing if src >= end
  CLC
  ADC16 BUF_PTR16, BUF_LEN16, BUF_SRC16
  CP16 BUF_PTR16, BUF_DST16
  CP16 BUF_END16, BUF_PTR16
  JSR mem_copy_down

  ; Update buffer end: subtract BUF_LEN16
  SEC
  SBC16 BUF_END16, BUF_LEN16, BUF_END16

  RTS

; Append a '\n' at BUF_END16 and advance it
; Clobbers: A, Y (Y = 0)
buf_append_nl:
  LDY #0
  LDA #'\n'
  STA (BUF_END16),Y
  INC16 BUF_END16
  RTS

; If the buffer is empty, append a newline (one empty line), then
; rebuild the line table (falls through into buf_rebuild_lines)
buf_ensure_nonempty_rebuild:
  LDA BUF_END16              ; TEXT_BUF is page-aligned
  BNE buf_rebuild_lines
  LDA BUF_END16 + 1
  CMP #>TEXT_BUF
  BNE buf_rebuild_lines
  JSR buf_append_nl
  ; fall through

; Rebuild line pointer table by scanning for newlines
; Sets LINE_COUNT16 and fills LINE_TBL.  Text past line MAX_LINES is cut
; off the buffer and READONLY is set, so the table never overflows (a
; load truncates a longer file like this; edits check first, with
; check_line_room)
buf_rebuild_lines:
  SET16 $0000, LINE_COUNT16
  SET16 TEXT_BUF, BUF_PTR16
  SET16 LINE_TBL, BUF_DST16

  ; First line starts at TEXT_BUF
  JSR store_line_entry

.scan_loop:
  ; Check if we've reached the end
  JSR cmp_ptr_end
  BCS .scan_done

.scan_byte:
  LDY #0
  LDA (BUF_PTR16),Y
  INC16 BUF_PTR16

  CMP #'\n'
  BNE .scan_loop

  ; Found a newline - check if there's more text after it
  JSR cmp_ptr_end
  BCS .scan_done

.add_line:
  ; Stop if the table already holds MAX_LINES lines
  LDA LINE_COUNT16
  CMP #<MAX_LINES
  LDA LINE_COUNT16 + 1
  SBC #>MAX_LINES
  BCS .table_full

  ; Advance line table pointer (LINE_TBL is even, so the low byte wraps
  ; to 0 exactly at a page end)
  INC BUF_DST16
  INC BUF_DST16
  BNE .store
  INC BUF_DST16 + 1
.store:
  ; Store line start pointer
  JSR store_line_entry

  JMP .scan_loop

.table_full:
  ; Cut the buffer at the start of the line that does not fit
  CP16 BUF_PTR16, BUF_END16
  DEC READONLY               ; Nonzero: read-only
.scan_done:
  RTS

; Store BUF_PTR16 into the line table entry at BUF_DST16, count the line
; Clobbers: A, Y (Y = 1)
store_line_entry:
  LDY #0
  LDA BUF_PTR16
  STA (BUF_DST16),Y
  INY
  LDA BUF_PTR16 + 1
  STA (BUF_DST16),Y
  INC16 LINE_COUNT16
  RTS

; Compare BUF_PTR16 with BUF_END16 (CMP16 semantics: C/Z as after CMP)
; Clobbers: A
cmp_ptr_end:
  LDA BUF_PTR16 + 1
  CMP BUF_END16 + 1
  BNE .d
  LDA BUF_PTR16
  CMP BUF_END16
.d:
  RTS

; Add the 16-bit signed delta in BUF_SRC16 to the line pointers of every
; line after FILE_LINE16 (single-line edits that add/remove no newlines)
; Clobbers: A, X, Y, BUF_PTR16, BUF_LEN16
buf_adjust_lines_apply:
  ; Count = LINE_COUNT16 - FILE_LINE16 - 1 (CLC: SBC subtracts one more)
  CLC
  SBC16 LINE_COUNT16, FILE_LINE16, BUF_LEN16
  BMI .done                  ; FILE_LINE16 >= LINE_COUNT16: nothing to do
  ORA BUF_LEN16
  BEQ .done                  ; Cursor on last line: nothing to adjust
  ; Entry address = LINE_TBL + (FILE_LINE16 + 1) * 2, split into a
  ; page-aligned base in BUF_PTR16 and the low byte in Y
  LDA FILE_LINE16 + 1
  STA BUF_PTR16 + 1
  LDA FILE_LINE16
  SEC
  ROL                        ; A = low(line * 2 + 1), C = bit 7
  ROL BUF_PTR16 + 1          ; C = 0 (line < $8000)
  ADC #1
  TAY                        ; Y = low(line * 2 + 2)
  LDA BUF_PTR16 + 1
  ADC #>LINE_TBL
  STA BUF_PTR16 + 1
  LDA #0
  STA BUF_PTR16
  ; Loop count: X = low byte, BUF_LEN16+1 = remaining 256-entry rounds
  LDX BUF_LEN16
  BEQ .loop
  INC BUF_LEN16 + 1
.loop:
  CLC
  LDA (BUF_PTR16),Y
  ADC BUF_SRC16
  STA (BUF_PTR16),Y
  INY
  LDA (BUF_PTR16),Y
  ADC BUF_SRC16 + 1
  STA (BUF_PTR16),Y
  INY
  BNE .same_page
  INC BUF_PTR16 + 1
.same_page:
  DEX
  BNE .loop
  DEC BUF_LEN16 + 1
  BNE .loop
.done:
  RTS
