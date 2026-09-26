; Mark storage and operations
;
; Stores line-oriented marks (a-z) as 16-bit line numbers.
; Marks are stored in MARK_TBL at $DF20 (52 bytes: 26 entries x 2 bytes).
; MARK_UNSET ($FFFF) indicates an unset mark. A mark is unset iff its high
; byte has bit 7 set: set marks are line numbers, which stay far below $8000
; (LINE_TBL at $D800 runs out long before that).

MARK_TBL   = $D620    ; 26 entries x 2 bytes = 52 bytes
MARK_UNSET = $FFFF

  .zeropage
MARK_DELTA16: .word
  .code

; Initialize all 26 marks to MARK_UNSET ($FFFF)
mark_init:
  LDX #51              ; 26*2 - 1
  LDA #$FF
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

  LDA #0
  STA BUF_TEMP           ; Mark index (0-25)
  STA BUF_DELTA          ; Count of marks displayed (init 0 since row 2 != 0)
  LDA #2
  STA ANSI_ROW           ; Start at row 2

.marks_loop:
  LDA BUF_TEMP
  ASL
  TAX

  ; Skip unset marks (both bytes $FF)
  LDA MARK_TBL + 1,X
  AND MARK_TBL,X
  CMP #$FF
  BNE .marks_set
  JMP .marks_next        ; (out of BEQ range)
.marks_set:

  ; Save mark table offset on stack
  TXA
  PHA

  ; Position cursor
  LDA #1
  STA ANSI_COL
  JSR ansi_move_cursor

  ; Print " a" (mark letter)
  LDA #' '
  JSR io_write
  LDA BUF_TEMP
  CLC
  ADC #'a'
  JSR io_write

  ; Restore table offset, get line number
  PLA
  TAX
  LDA MARK_TBL,X
  STA TO_DECIMAL_VALUE16
  LDA MARK_TBL + 1,X
  STA TO_DECIMAL_VALUE16 + 1

  ; Save line for text lookup (before INC16 modifies it)
  PUSH16 TO_DECIMAL_VALUE16

  ; Print right-justified 1-based line number in 6-char field
  INC16 TO_DECIMAL_VALUE16
  JSR to_decimal
  JSR write_decimal_rjust

  ; Print 1 space before text
  LDA #' '
  JSR io_write

  ; Get saved line number, print text
  POP16 BUF_PTR16
  CMP16 BUF_PTR16, LINE_COUNT16
  BCS .marks_text_done
  LDAX16 BUF_PTR16
  JSR buf_get_line_ptr
  ; Compute text width limit: SCREEN_COLS - 10 (2 " a" + 6 number + 2 spaces)
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
  JMP .marks_text
.marks_text_done:

  INC ANSI_ROW
  INC BUF_DELTA

  ; Check screen full
  LDA ANSI_ROW
  CLC
  ADC #1
  CMP SCREEN_ROWS
  BCS .marks_done_display

.marks_next:
  INC BUF_TEMP
  LDA BUF_TEMP
  CMP #26
  BEQ .marks_done_display
  JMP .marks_loop

.marks_done_display:
  LDA BUF_DELTA
  BNE .marks_wait
  LDA #2
  STA ANSI_ROW
  LDA #1
  STA ANSI_COL
  JSR ansi_move_cursor
  PRINT_STR str_no_marks

.marks_wait:
  JSR flush_get_key
  LDA #$FF
  STA RENDER_FLAG
  RTS

; Print TO_DECIMAL_RESULT right-justified in a 6-character field
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
  ; Print (6 - X) spaces
  LDA #' '
.pad_loop:
  CPX #6 + 1
  BEQ .print
  JSR io_write
  INX
  BNE .pad_loop   ; Always taken
.print:
  JSR print_decimal_result
  RTS

str_marks_header: .asciiz "mark line text"
str_no_marks:     .asciiz "No marks set"

; Adjust marks based on line range and operation
; Input: BUF_SRC16 = start_line
;        BUF_DST16 = end_line (for delete) or start_line (for insert)
;        BUF_TEMP16 = count (16-bit)
;        Carry flag: clear = add (insert), set = subtract (delete)
; Clobbers: A, X, Y
mark_adjust_range:
  ; Prepare delta: positive for insert, negative for delete
  LDA BUF_TEMP16
  STA MARK_DELTA16
  LDA BUF_TEMP16 + 1
  STA MARK_DELTA16 + 1
  BCC .loop_start      ; Insert: use +count as-is

  ; Delete: negate MARK_DELTA16 (2's complement)
  SEC
  LDA #0
  SBC MARK_DELTA16
  STA MARK_DELTA16
  LDA #0
  SBC MARK_DELTA16 + 1
  STA MARK_DELTA16 + 1

.loop_start:
  LDX #0               ; Index into MARK_TBL
.loop:
  ; Skip unset marks (both bytes $FF)
  LDA MARK_TBL + 1,X
  AND MARK_TBL,X
  CMP #$FF
  BEQ .next

  ; Compare mark >= end_line (BUF_DST16)?
  LDA MARK_TBL + 1,X
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
  ; Mark in [start, end): unset
  LDA #$FF
  STA MARK_TBL,X
  STA MARK_TBL + 1,X
  JMP .next

.adjust:
  ; Mark >= end_line: add MARK_DELTA16 (positive for insert, negative for delete)
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
  BCS mark_adjust_delete
  JMP mark_adjust_insert

; Insert 1 line at A/X, adjust marks
mark_insert_one:
  PHA
  JSR set_buf_temp16_one
  PLA
  JMP mark_adjust_insert

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

; Adjust marks after lines are deleted
; Input: A/X = first deleted line (16-bit low/high)
;        BUF_TEMP16 = count of deleted lines (16-bit)
; Marks on [first_line, first_line+count): unset
; Marks >= first_line+count: subtract count
; Clobbers: A, X, Y
mark_adjust_delete:
  ; Store first_line in BUF_SRC16
  STAX16 BUF_SRC16

  ; Compute end_line = first_line + count -> BUF_DST16
  CLC
  ADC16 BUF_SRC16, BUF_TEMP16, BUF_DST16

  SEC                  ; Set carry for subtract
  JMP mark_adjust_range

; Adjust marks after lines are inserted
; Input: A/X = at_line (16-bit low/high), BUF_TEMP16 = count of inserted lines (16-bit)
; Marks >= at_line: add count
; Clobbers: A, X, Y
mark_adjust_insert:
  ; Store at_line in BUF_SRC16
  STAX16 BUF_SRC16

  ; Set DST = SRC (empty unset range for insert)
  LDA BUF_SRC16
  STA BUF_DST16
  LDA BUF_SRC16 + 1
  STA BUF_DST16 + 1

  CLC                  ; Clear carry for add
  JMP mark_adjust_range
