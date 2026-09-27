; Text buffer data structure and operations
;
; Memory layout:
;   TEXT_BUF           - Start of text buffer (page-aligned, past end of code)
;   LINE_TBL ($D800)   - Line pointer table (16-bit pointers, room for 1024)
;
; The text buffer stores all text contiguously. Lines are delimited by $0A.
; The line table stores 16-bit pointers to the start of each line, then
; the end of the text (BUF_END16), so a line's length is the gap to the
; next entry.
; Insertions/deletions shift all text after the edit point.
;
; TEXT_BUF and TEXT_LIMIT are defined at the end of editor.asm as floating
; labels, so TEXT_BUF automatically adjusts as the code grows.

LINE_TBL    = $D800  ; Line pointer table (2 bytes per entry)
MAX_LINES   = $03FF  ; Most lines a buffer holds (1023: LINE_TBL has room
                     ; for 1024 entries, the last for the end of the text)
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
  JSR buf_ensure_nonempty ; An empty file has no lines
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
  JMP buf_rebuild_lines

; Get pointer to start of line N (N in A/X, low/high); for N =
; LINE_COUNT16 the entry after the last line gives BUF_END16
; Returns pointer in BUF_PTR16
; Clobbers A, Y
buf_get_line_ptr:
  JSR buf_line_entry
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

; BUF_PTR16 = the address of line N's LINE_TBL entry (N in A/X): LINE_TBL
; + N * 2 (LINE_TBL is page-aligned and N < $8000, so the ROL leaves
; C = 0 for the high-byte add).  Clobbers A
buf_line_entry:
  STA BUF_PTR16
  TXA
  ASL BUF_PTR16
  ROL
  ADC #>LINE_TBL
  STA BUF_PTR16 + 1
  RTS

; Get length of line N (N in A/X, low/high, below LINE_COUNT16), not
; counting the newline: the start of line N + 1 (for the last line, the
; end of the text in the entry after it) - the start of line N - 1
; Returns 16-bit length in A (low) / X (high)
; Clobbers Y, BUF_PTR16
buf_get_line_len:
  JSR buf_line_entry
  LDY #2
  LDA (BUF_PTR16),Y          ; Start of line N + 1
  LDY #0
  CLC                        ; (The borrow drops the newline)
  SBC (BUF_PTR16),Y          ; - start of line N - 1
  PHA
  LDY #3
  LDA (BUF_PTR16),Y
  LDY #1
  SBC (BUF_PTR16),Y
  TAX
  PLA
  RTS

; BUF_PTR16 += A.  Clobbers A; preserves X, Y
ptr_add_a:
  CLC
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
  LSR EMPTY_BUF    ; A line of the text now (bit 6: it was none)

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
  JSR ptr_to_src             ; BUF_SRC16 = start of the first line
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

; If the buffer is empty, append a newline (one empty line, which
; EMPTY_BUF marks as no lines of the text: vim's ML_EMPTY).  Clobbers A,
; Y
buf_ensure_nonempty:
  LDA BUF_END16              ; TEXT_BUF is page-aligned
  BNE .done
  LDA BUF_END16 + 1
  CMP #>TEXT_BUF
  BNE .done
  JSR buf_append_nl
  ROR EMPTY_BUF              ; (C = 1 from the compare)
.done:
  RTS

; The same, then rebuild the line table (falls through into
; buf_rebuild_lines)
buf_ensure_nonempty_rebuild:
  JSR buf_ensure_nonempty
  ; fall through

; Rebuild line pointer table by scanning for newlines, from the cursor
; line on: every edit changes the text only from the start of line
; FILE_LINE16 (at most LINE_COUNT16) on, so the entries up to that
; line's own still hold (at startup FILE_LINE16 is 0, and editor_main has
; set line 0's entry).  Sets LINE_COUNT16 and fills LINE_TBL, then
; stores the end of the text in the entry after the last line.  Text
; past line MAX_LINES is cut off the buffer and READONLY is set, so the
; table never overflows (a load truncates a longer file like this; edits
; check first, with check_line_room).  The text ends with a newline, so
; the end is tested only at line starts.  TEXT_BUF and LINE_TBL are
; page-aligned: the scan is at (page, Y) with the page in BUF_PTR16 + 1,
; and the entries are stored through (BUF_DST16,X) with X = 0.
; Clobbers A, X, Y, BUF_PTR16, BUF_DST16
buf_rebuild_lines:
  ; LINE_COUNT16 = the lines before FILE_LINE16, BUF_DST16 = its entry
  LDA FILE_LINE16
  STA LINE_COUNT16
  ASL
  STA BUF_DST16
  LDA FILE_LINE16 + 1
  STA LINE_COUNT16 + 1
  ROL
  ADC #>LINE_TBL             ; (C = 0: FILE_LINE16 < $8000)
  STA BUF_DST16 + 1
  ; (page, Y) = the start of line FILE_LINE16
  LDX #0
  STX BUF_PTR16
  LDY #1
  LDA (BUF_DST16),Y
  STA BUF_PTR16 + 1
  LDA (BUF_DST16,X)
  TAY
.entry:
  ; Store (page, Y) in the next entry
  TYA
  STA (BUF_DST16,X)
  INC BUF_DST16
  LDA BUF_PTR16 + 1
  STA (BUF_DST16,X)
  INC BUF_DST16
  BNE .stored
  INC BUF_DST16 + 1
.stored:
  ; At BUF_END16 that entry ends the last line (past it only if the text
  ; lacks its final newline: the scan then found the next one)
  CPY BUF_END16
  SBC BUF_END16 + 1          ; C = (page, Y) >= BUF_END16
  BCS .done
  ; Otherwise a line starts there, unless the table holds MAX_LINES lines
  ; already (the entry after them ends a page: MAX_LINES + 1 is even)
  LDA BUF_DST16 + 1
  CMP #>LINE_TBL+MAX_LINES+MAX_LINES+$02
  BCS .table_full
  INC16 LINE_COUNT16
.scan:
  LDA (BUF_PTR16),Y
  INY
  BEQ .next_page
.test:
  CMP #'\n'
  BNE .scan
  BEQ .entry                 ; Always: a line (or the end) follows it
.next_page:
  INC BUF_PTR16 + 1
  BNE .test                  ; Always (the text ends below $FF00)

.table_full:
  ; Cut the buffer at the start of the line that does not fit (the entry
  ; just stored then ends the last line)
  STY BUF_END16
  LDA BUF_PTR16 + 1
  STA BUF_END16 + 1
  DEC READONLY               ; Nonzero: read-only
.done:
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

; Move the lines after FILE_LINE16 by BUF_LEN16, the bytes an insert of
; no newlines put in it (buf_adjust_lines_apply).  Also clobbers BUF_SRC16
buf_adjust_lines_len:
  CP16 BUF_LEN16, BUF_SRC16
  ; fall through

; Add the 16-bit signed delta in BUF_SRC16 to the line pointers of every
; line after FILE_LINE16 and to the entry after the last line (the end of
; the text), for single-line edits that add/remove no newlines
; Clobbers: A, X, Y, BUF_PTR16, BUF_LEN16 + 1
buf_adjust_lines_apply:
  LDX FILE_LINE16 + 1
  LDY FILE_LINE16
  INY
  TYA
  BNE buf_adjust_lines_from
  INX
  ; fall through

; The same for the entries of lines A/X (low/high) to LINE_COUNT16 (the
; end of the text): none if A/X is past it
buf_adjust_lines_from:
  STA BUF_PTR16
  STX BUF_PTR16 + 1
  ; Loop count: A/X - LINE_COUNT16 - 1, the entries negated, counted up
  ; to 0 in X (low byte) and BUF_LEN16 + 1 (high byte)
  CLC
  SBC LINE_COUNT16
  TAX
  LDA BUF_PTR16 + 1
  SBC LINE_COUNT16 + 1
  STA BUF_LEN16 + 1
  BCS .done                  ; A/X past LINE_COUNT16: none
  ; Entry address = LINE_TBL + A/X * 2, split into a page-aligned base
  ; in BUF_PTR16 and the low byte in Y (C = 0 after the ROL: A/X < $8000)
  ASL BUF_PTR16
  ROL BUF_PTR16 + 1
  LDA BUF_PTR16 + 1
  ADC #>LINE_TBL
  STA BUF_PTR16 + 1
  LDY BUF_PTR16
  LDA #0
  STA BUF_PTR16
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
  INX
  BNE .loop
  INC BUF_LEN16 + 1
  BNE .loop
.done:
  RTS

; Save buffer to file
; File handle in A (already opened for write)
; Writes every byte from TEXT_BUF to BUF_END16, including the final
; newline, but none for a buffer with no lines (EMPTY_BUF, as vim writes
; it), which is then one line break
buf_save_file:
  STA FILE_HANDLE
  LDY #0                  ; Y = page offset, set once
  STY BUF_PTR16           ; BUF_PTR16 = TEXT_BUF (page-aligned)
  LDA #>TEXT_BUF
  STA BUF_PTR16 + 1
  BIT EMPTY_BUF
  BPL .write_loop
  LDX BUF_END16
  DEX
  BNE .write_loop
  CMP BUF_END16 + 1
  BEQ .write_done         ; No lines: no bytes
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
