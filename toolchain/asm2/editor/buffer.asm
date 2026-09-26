; Text buffer data structure and operations
;
; Memory layout:
;   TEXT_BUF           - Start of text buffer (page-aligned, past end of code)
;   LINE_TBL ($D800)   - Line pointer table (16-bit offsets, max 1024 lines)
;
; The text buffer stores all text contiguously. Lines are delimited by $0A.
; The line table stores 16-bit pointers to the start of each line.
; Insertions/deletions shift all text after the edit point.
;
; TEXT_BUF and TEXT_LIMIT are defined at the end of editor.asm as floating
; labels, so TEXT_BUF automatically adjusts as the code grows.

LINE_TBL    = $D800  ; Line pointer table (2 bytes per entry)
MAX_LINES   = $03FF  ; Maximum line count (1023), 0-indexed
BATCH_BUF   = $D600  ; Staging buffer for batch insert (32 bytes)
BATCH_MAX   = 32     ; Maximum batch size

  .zeropage

BUF_END16:     .word     ; Points one past last byte of text
LINE_COUNT16:  .word     ; Number of lines in buffer (16-bit)
BUF_PTR16:     .word     ; General-purpose buffer pointer
BUF_SRC16:     .word     ; Source pointer for block moves
BUF_DST16:     .word     ; Destination pointer for block moves
BUF_LEN16:     .word     ; Length/count for block moves
BUF_TEMP:      .byte     ; Temp byte for buffer operations
BUF_TEMP16:    .word     ; 16-bit count for line operations (delete, yank, etc.)
BUF_DELTA:     .byte     ; Shift amount for block moves
FILE_HANDLE:   .byte     ; File handle for load/save
BUF_LIMIT:     .byte     ; High byte of buffer limit (default >TEXT_LIMIT)

  .code

; Initialize empty buffer
; Sets up an empty buffer with one empty line
buf_init:
  SET16 TEXT_BUF, BUF_END16
  ; Empty buffer: appends a newline for one empty line, builds line table
  JMP buf_ensure_nonempty_rebuild

; Load file into buffer
; File handle in A (already opened)
; On return: buffer contains file contents, line table built
; BUF_TEMP = $FF if the file was truncated, $00 if fully loaded
buf_load_file:
  STA FILE_HANDLE
  SET16 TEXT_BUF, BUF_END16
  LDA #0
  STA BUF_TEMP            ; Clear truncation flag

  LDY #0                  ; Y = page offset, set once
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
  CMP BUF_LIMIT
  BCC .read_loop
  ; Buffer full - file was truncated
  LDA #$FF
  STA BUF_TEMP
.read_done:
  STY BUF_END16           ; Reconstruct full pointer
  ; Ensure buffer ends with newline
  SEC
  SBCI16 BUF_END16, $0001, BUF_PTR16

  ; Check if last byte is newline
  LDY #0
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .has_newline
  ; Need to add a newline
  LDA BUF_TEMP
  BNE .overwrite_last
  ; Not truncated - append trailing newline
  JSR buf_append_nl
  JMP .has_newline
.overwrite_last:
  ; Truncated - overwrite last byte to stay within buffer limit
  LDA #'\n'
  LDY #0
  STA (BUF_PTR16),Y
.has_newline:

  ; If buffer is empty (nothing read), add a newline for one empty line
  JMP buf_ensure_nonempty_rebuild

; Save buffer to file
; File handle in A (already opened for write)
; Writes all text except the final trailing newline of the last empty line
buf_save_file:
  STA FILE_HANDLE
  SET16 TEXT_BUF, BUF_PTR16

  LDY #0                  ; Y = page offset, set once
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
  JMP .write_loop
.write_done:
  RTS

; Get pointer to start of line N (N in A/X, low/high)
; Returns pointer in BUF_PTR16
; Clobbers A, Y
buf_get_line_ptr:
  ; Line table index = N * 2
  STAX16 BUF_PTR16
  ASL16 BUF_PTR16
  ; Add LINE_TBL base
  CLC
  ADCI16 BUF_PTR16, LINE_TBL, BUF_PTR16
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
; Clobbers Y
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
  JMP .loop
.done:
  RTS

; Scan (BUF_PTR16) for newline, then advance BUF_PTR16 past it
; Input: BUF_PTR16 = scan start
; Output: BUF_PTR16 = address after the newline
; Clobbers: A, X, Y
advance_past_line_end:
  JSR find_line_end
  INY
  BNE .no_wrap
  INC BUF_PTR16 + 1
.no_wrap:
  TYA
  CLC
  ADCA16 BUF_PTR16, BUF_PTR16
  RTS

; Insert character at position in buffer
; A = character to insert
; BUF_PTR16 = position to insert at
; Shifts all following bytes right by 1
; Returns carry set = buffer full, carry clear = success
buf_insert_char:
  PHA
  LDA #1
  STA BUF_LEN16
  LDA #0
  STA BUF_LEN16 + 1
  JSR buf_shift_right_16
  PLA
  BCS .done                  ; Buffer full (carry preserved for caller)
  LDY #0
  STA (BUF_PTR16),Y
.done:
  RTS

; Shift buffer right by BUF_LEN16 bytes at BUF_PTR16 (16-bit version)
; Input: BUF_PTR16 = insert point, BUF_LEN16 = shift amount (16-bit)
; Returns carry set = buffer full, carry clear = success
; Updates BUF_END16 on success. Does not modify BUF_PTR16.
buf_shift_right_16:
  ; Check if buffer has room for BUF_LEN16 bytes
  CLC
  LDA BUF_END16
  ADC BUF_LEN16
  STA BUF_DST16              ; Temp: new end low
  LDA BUF_END16 + 1
  ADC BUF_LEN16 + 1
  CMP BUF_LIMIT
  BCC .has_room
  BNE .full
  LDA BUF_DST16
  BEQ .has_room         ; Exactly at limit is ok
.full:
  SEC
  RTS
.has_room:

  ; Check if nothing to move (insert at end; equality-only test)
  JSR cmp_ptr_end
  BEQ .shift_done

  ; Set up mem_copy_up parameters:
  ;   BUF_SRC16 = source start (insert point = BUF_PTR16)
  ;   BUF_DST16 = destination (insert point + shift amount)
  ;   BUF_PTR16 = source end (BUF_END16)
  ; Save BUF_PTR16 (callers need it preserved)
  PUSH16 BUF_PTR16
  CP16 BUF_PTR16, BUF_SRC16
  CLC
  ADC16 BUF_SRC16, BUF_LEN16, BUF_DST16
  CP16 BUF_END16, BUF_PTR16
  JSR mem_copy_up
  POP16 BUF_PTR16

.shift_done:
  ; Update buffer end: add BUF_LEN16
  CLC
  ADC16 BUF_END16, BUF_LEN16, BUF_END16

  CLC              ; Success
  RTS

; Delete N contiguous lines starting at line A/X
; Input: A/X = first line number (low/high), BUF_TEMP16 = count of lines to delete (16-bit)
; Handles end-of-file clamping, empty buffer, rebuilds line table once
buf_delete_lines:
  ; Save first line number
  STAX16 BUF_DST16

  ; Get pointer to start of first line
  JSR buf_get_line_ptr       ; BUF_PTR16 = start of first line
  PUSH16 BUF_PTR16           ; Save dest pointer on stack

  ; Calculate line number after last deleted: first + count
  CLC
  ADC16 BUF_DST16, BUF_TEMP16, BUF_SRC16  ; BUF_SRC16 = end line number

  ; If end line >= LINE_COUNT16, source = BUF_END16
  CMP16 BUF_SRC16, LINE_COUNT16
  BCC .get_end_ptr
  CP16 BUF_END16, BUF_SRC16
  JMP .have_source

.get_end_ptr:
  ; Get pointer to line after last deleted
  LDAX16 BUF_SRC16
  JSR buf_get_line_ptr       ; BUF_PTR16 = start of end line
  CP16 BUF_PTR16, BUF_SRC16

.have_source:
  ; BUF_SRC16 = source address (data to keep)
  POP16 BUF_PTR16            ; BUF_PTR16 = dest (start of deleted region)

  ; Calculate shift amount: BUF_LEN16 = BUF_SRC16 - BUF_PTR16
  SEC
  SBC16 BUF_SRC16, BUF_PTR16, BUF_LEN16

  ; Shift left by BUF_LEN16 bytes
  JSR buf_shift_left_16

  ; If buffer is now empty, add a newline; rebuild line table
  JMP buf_ensure_nonempty_rebuild

; Shift buffer left by BUF_LEN16 bytes at BUF_PTR16 (16-bit version)
; Input: BUF_PTR16 = delete point, BUF_LEN16 = shift amount (16-bit)
; Updates BUF_END16 on completion
buf_shift_left_16:
  ; Compute source start = BUF_PTR16 + BUF_LEN16
  CLC
  ADC16 BUF_PTR16, BUF_LEN16, BUF_SRC16

  ; Check if nothing to move (source >= BUF_END16)
  LDA BUF_SRC16 + 1
  CMP BUF_END16 + 1
  BCC .need_shift
  BNE .shift_done
  LDA BUF_SRC16
  CMP BUF_END16
  BCS .shift_done
.need_shift:

  ; Set up mem_copy_down parameters:
  ;   BUF_SRC16 = source start (already set above)
  ;   BUF_DST16 = destination (delete point = original BUF_PTR16)
  ;   BUF_PTR16 = source end (BUF_END16)
  CP16 BUF_PTR16, BUF_DST16
  CP16 BUF_END16, BUF_PTR16
  JSR mem_copy_down

.shift_done:
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
  CMPI16 BUF_END16, TEXT_BUF
  BNE buf_rebuild_lines
  JSR buf_append_nl
  ; fall through

; Rebuild line pointer table by scanning for newlines
; Sets LINE_COUNT16 and fills LINE_TBL
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
  ; Advance line table pointer
  CLC
  ADCI16 BUF_DST16, $0002, BUF_DST16

  ; Store line start pointer
  JSR store_line_entry

  JMP .scan_loop

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

; Common setup for buf_adjust_lines_inc/dec
; Calculates count = LINE_COUNT16 - FILE_LINE16 - 1
; Computes BUF_PTR16 = LINE_TBL entry for FILE_LINE16 + 1
; Returns carry set if nothing to do (count <= 0)
; Clobbers: A
buf_adjust_lines_setup:
  ; Calculate number of entries to adjust: LINE_COUNT16 - FILE_LINE16 - 1
  SEC
  SBC16 LINE_COUNT16, FILE_LINE16, BUF_LEN16

  ; Subtract 1 (we start from line+1, not line)
  DEC16 BUF_LEN16

  ; If count <= 0, nothing to adjust
  LDA BUF_LEN16 + 1
  BMI .nothing
  ORA BUF_LEN16
  BEQ .nothing

  ; Calculate LINE_TBL entry for (FILE_LINE16 + 1)
  ; Entry address = LINE_TBL + (FILE_LINE16 + 1) * 2
  CLC
  ADCI16 FILE_LINE16, $0001, BUF_PTR16
  ASL16 BUF_PTR16
  CLC
  ADCI16 BUF_PTR16, LINE_TBL, BUF_PTR16

  CLC              ; Has work to do
  RTS
.nothing:
  SEC              ; Nothing to do
  RTS

; Decrement line pointers after current line by BUF_DELTA
; Input: FILE_LINE16 = current line number, BUF_DELTA = shift amount
; Clobbers: A, Y
buf_adjust_lines_dec:
  LDA #0
  SEC
  SBC BUF_DELTA
  STA BUF_SRC16
  LDA #$FF
  STA BUF_SRC16 + 1
  JMP buf_adjust_lines_apply

; Increment line pointers after current line by BUF_DELTA
; Input: FILE_LINE16 = current line number, BUF_DELTA = shift amount
; Clobbers: A, Y
buf_adjust_lines_inc:
  LDA BUF_DELTA
  STA BUF_SRC16
  LDA #0
  STA BUF_SRC16 + 1
  ; Fall through

; Apply 16-bit signed delta in BUF_SRC16 to line pointers after current line
buf_adjust_lines_apply:
  JSR buf_adjust_lines_setup
  BCS .done
  LDY BUF_PTR16              ; Y = offset within page
  LDA #0
  STA BUF_PTR16              ; BUF_PTR16 = page-aligned base
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
  BEQ .page_cross
.back:
  DEC16 BUF_LEN16
  TST16 BUF_LEN16
  BNE .loop
.done:
  RTS
.page_cross:
  INC BUF_PTR16 + 1
  JMP .back

; Find line number and column for a buffer address
; Input: BUF_PTR16 = target buffer address (within TEXT_BUF..BUF_END16)
; Output: FILE_LINE16 = line number, CURSOR_COL16 = column
; Clobbers: A, Y, BUF_SRC16, BUF_DST16
find_line_for_ptr:
  LDA #0
  STA_LH16 FILE_LINE16
  SET16 LINE_TBL, BUF_SRC16        ; scan pointer into LINE_TBL
.loop:
  ; If no next line, target must be on current line
  CLC
  ADCI16 FILE_LINE16, 1, BUF_DST16
  CMP16 BUF_DST16, LINE_COUNT16
  BCS .found
  ; Read next line's start address from LINE_TBL
  LDY #2
  LDA (BUF_SRC16),Y
  TAX
  INY
  LDA (BUF_SRC16),Y                ; A:X = next line start (hi:lo)
  ; If next_line_start > target, target is on current line
  CMP BUF_PTR16 + 1
  BCC .advance
  BNE .found
  CPX BUF_PTR16
  BEQ .advance                     ; target == next line start -> it's on next line
  BCS .found
.advance:
  INC16 FILE_LINE16
  CLC
  ADCI16 BUF_SRC16, 2, BUF_SRC16
  JMP .loop
.found:
  ; CURSOR_COL16 = target - LINE_TBL[FILE_LINE16]
  LDY #0
  SEC
  LDA BUF_PTR16
  SBC (BUF_SRC16),Y
  STA CURSOR_COL16
  INY
  LDA BUF_PTR16 + 1
  SBC (BUF_SRC16),Y
  STA CURSOR_COL16 + 1
  RTS
