; Mark storage and operations
;
; Stores line-oriented marks (a-z) as 16-bit line numbers.
; Marks are stored in MARK_TBL at $D620 (52 bytes: 26 entries x 2 bytes).
; mark_init sets every entry to MARK_UNSET ($FFFF). A mark is unset iff its
; high byte has bit 7 set: set marks are line numbers, which stay far below
; $8000 (LINE_TBL at $D800 runs out long before that), and mark_adjust
; unsets a mark by storing $FF in its high byte only.

MARK_TBL   = $D620    ; 26 entries x 2 bytes = 52 bytes
MARK_UNSET = $FFFF

; (zero-page variables: zp.asm)

; Initialize all 26 marks to MARK_UNSET ($FFFF)
mark_init:
  LDX #51              ; 26*2 - 1
  LDA #<MARK_UNSET     ; (both bytes are $FF)
.loop:
  STA MARK_TBL,X
  DEX
  BPL .loop
  RTS

; Calculate the table offset for a mark
; Input: A - mark name ('a'-'z')
; Returns: carry clear, A = table offset (0-50)
;          carry set if invalid name
mark_calculate_pointer_offset:
  SEC
  SBC #'a'
  CMP #26
  BCS .ret             ; Invalid (names below 'a' wrap above 25)
  ASL                  ; *2 for 16-bit entries; C = 0 since A < 26
.ret:
  RTS

; Set mark: store current FILE_LINE16 at mark position
; Input: A = mark name ('a'-'z')
; Returns: carry set if invalid name, carry clear if set
mark_set:
  JSR mark_calculate_pointer_offset
  BCS .ret
  TAX
  LDA FILE_LINE16
  STA MARK_TBL,X
  LDA FILE_LINE16 + 1
  STA MARK_TBL + 1,X
.ret:
  RTS                  ; Carry clear from the offset calculation

; Get mark: retrieve line number for mark
; Input: A = mark name ('a'-'z')
; Returns: A = low byte, X = high byte of line number
;          carry set if unset or invalid, carry clear if valid
; Clobbers: Y
mark_get:
  JSR mark_calculate_pointer_offset
  BCS .ret
  TAY
  LDX MARK_TBL + 1,Y
  CPX #$80             ; Unset iff the high byte has bit 7 set
  BCS .ret
  LDA MARK_TBL,Y
.ret:
  RTS

; Display all set marks
; Clears screen, prints mark/line/text table, waits for keypress
; Sets RENDER_FLAG = $FF on return (full redraw)
marks_display:
  JSR ansi_clear_screen
  PRINT_STR str_marks_header

  LDA #1
  STA ANSI_COL           ; Every row starts at column 1
  LDA #2
  STA ANSI_ROW           ; First mark row (still 2 at the end = none shown)
  LDA #'a'
  STA BUF_TEMP           ; Mark letter

.marks_loop:
  LDA BUF_TEMP
  JSR mark_get           ; A/X = line, carry set if unset
  BCS .marks_next
  STAX16 BUF_PTR16       ; 0-based line (survives the output calls below)

  ; Print " a" (mark letter)
  JSR ansi_move_cursor
  LDA #' '
  JSR io_write
  LDA BUF_TEMP
  JSR io_write

  ; Print the 1-based line number right-justified in a 7-char field,
  ; then one space
  CLC
  ADCI16 BUF_PTR16, $0001, TO_DECIMAL_VALUE16
  JSR to_decimal
  JSR write_decimal_rjust
  LDA #' '
  JSR io_write

  ; Print the line text (if the line still exists)
  CMP16 BUF_PTR16, LINE_COUNT16
  BCS .marks_text_done
  LDAX16 BUF_PTR16
  JSR buf_get_line_ptr
  ; Text width limit: SCREEN_COLS - 10 (" a" + 7-char number + 1 space)
  LDA SCREEN_COLS
  SEC
  SBC #10
  STA LINE_LEN16
  LDY #0
.marks_text:
  CPY LINE_LEN16
  BCS .marks_text_done
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .marks_text_done
  CMP #' '
  BCS .marks_text_ok
  LDA #' '
.marks_text_ok:
  JSR io_write
  INY
  BNE .marks_text        ; Always taken (limit < 256)
.marks_text_done:

  ; Stop before the last two rows (the next row would be SCREEN_ROWS-1)
  INC ANSI_ROW
  LDX ANSI_ROW
  CPX TEXT_ROWS
  BCS .marks_done_display

.marks_next:
  INC BUF_TEMP
  LDA BUF_TEMP
  CMP #'z' + 1
  BNE .marks_loop

.marks_done_display:
  LDA ANSI_ROW
  CMP #2
  BNE .marks_wait        ; At least one mark shown
  JSR ansi_move_cursor   ; Row 2, column 1
  PRINT_STR str_no_marks

.marks_wait:
  JSR flush_get_key
  LDA #RF_FULL
  STA RENDER_FLAG
  RTS

; Print TO_DECIMAL_RESULT right-justified in a 7-character field
; Clobbers: A, X, Y
write_decimal_rjust:
  ; Count digits
  LDX #0
.count:
  LDA TO_DECIMAL_RESULT,X
  BEQ .pad
  INX
  BNE .count      ; Always taken
.pad:
  ; Print (7 - X) spaces
  LDA #' '
.pad_loop:
  CPX #6 + 1
  BEQ .print
  JSR io_write
  INX
  BNE .pad_loop   ; Always taken
.print:
  JMP print_decimal_result

str_marks_header: .asciiz "mark line text"
str_no_marks:     .asciiz "No marks set"

; Adjust marks with col-0 line adjustment via CURSOR_COL16
; At col 0: line consumed entirely, A/X unchanged
; At col > 0: line partially survives, A/X incremented
; Carry: set = delete, clear = insert
; Input: A/X = base line, BUF_TEMP16 = count
mark_adjust_col:
  PHP
  LDY CURSOR_COL16
  BNE .col_nz
  LDY CURSOR_COL16 + 1
  BEQ .dispatch
.col_nz:
  CLC
  ADC #1
  BCC .dispatch
  INX
.dispatch:
  PLP
  BCC mark_adjust_insert
  ; fall through

; Adjust marks after lines are deleted
; Input: A/X = first deleted line (16-bit low/high)
;        BUF_TEMP16 = count of deleted lines (16-bit)
; Marks on [first_line, first_line+count): unset
; Marks >= first_line+count: subtract count
; Clobbers: A, X, Y, BUF_SRC16, BUF_DST16, MARK_DELTA16
mark_adjust_delete:
  STAX16 BUF_SRC16
  CLC
  ADC16 BUF_SRC16, BUF_TEMP16, BUF_DST16   ; end_line = first + count
  SEC
  SBC16 BUF_SRC16, BUF_DST16, MARK_DELTA16 ; delta = -count
  JMP mark_adjust_range

; Insert 1 line at A/X, adjust marks
mark_insert_one:
  PHA
  JSR set_buf_temp16_one
  PLA
  ; fall through

; Adjust marks after lines are inserted
; Input: A/X = at_line (16-bit low/high), BUF_TEMP16 = count of inserted lines (16-bit)
; Marks >= at_line: add count
; Clobbers: A, X, Y, BUF_SRC16, BUF_DST16, MARK_DELTA16
mark_adjust_insert:
  STAX16 BUF_SRC16
  STAX16 BUF_DST16       ; Empty unset range
  CP16 BUF_TEMP16, MARK_DELTA16
  ; fall through

; Adjust marks for a line range
; Input: BUF_SRC16 = start_line, BUF_DST16 = end_line (exclusive)
;        MARK_DELTA16 = amount added to marks >= end_line
; Marks in [start_line, end_line) are unset.
; Clobbers: A, X
mark_adjust_range:
  LDX #0               ; Index into MARK_TBL
.loop:
  LDA MARK_TBL + 1,X
  BMI .next            ; Unset mark

  ; Compare mark >= end_line (BUF_DST16)?
  CMP BUF_DST16 + 1
  BCC .check_start      ; mark_hi < end_hi -> mark < end
  BNE .adjust           ; mark_hi > end_hi -> mark >= end
  LDA MARK_TBL,X
  CMP BUF_DST16
  BCS .adjust           ; mark_lo >= end_lo -> mark >= end

.check_start:
  ; Mark < end_line. Is mark >= start_line (BUF_SRC16)?
  LDA MARK_TBL + 1,X
  CMP BUF_SRC16 + 1
  BCC .next             ; mark_hi < start_hi -> skip
  BNE .unset            ; mark_hi > start_hi -> in range
  LDA MARK_TBL,X
  CMP BUF_SRC16
  BCC .next             ; mark_lo < start_lo -> skip

.unset:
  ; Mark in [start, end): unset (high byte $FF)
  LDA #$FF
  STA MARK_TBL + 1,X
  BNE .next             ; Always taken

.adjust:
  ; Mark >= end_line: add MARK_DELTA16
  CLC
  LDA MARK_TBL,X
  ADC MARK_DELTA16
  STA MARK_TBL,X
  LDA MARK_TBL + 1,X
  ADC MARK_DELTA16 + 1
  STA MARK_TBL + 1,X

.next:
  INX
  INX
  CPX #52              ; 26 * 2
  BNE .loop
  RTS

; Mark-adjust args for lines inserted or deleted after the cursor line:
; BUF_TEMP16 = A (line count), A/X = FILE_LINE16 + 1
; Clobbers: A, X, BUF_TEMP16
mark_args_next_line:
  JSR set_buf_temp16_a
  LDX FILE_LINE16 + 1
  LDA FILE_LINE16
  CLC
  ADC #1
  BCC .done
  INX
.done:
  RTS
