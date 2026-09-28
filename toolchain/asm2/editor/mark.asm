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
; Clears screen, prints the mark/line/text table a page at a time (as
; vim's more-prompt does: when the rows above the last are full and more
; marks follow, '-- More --' there waits for a key, and q ends the list),
; then waits for a keypress
; Sets RENDER_FLAG = $FF on return (full redraw)
marks_display:
  LDA #'a'
  STA BUF_TEMP           ; Mark letter
  JSR marks_page

.marks_loop:
  LDA BUF_TEMP
  JSR mark_get           ; A/X = line, carry set if unset
  BCS .marks_next
  STAX16 BUF_PTR16       ; 0-based line (survives the output calls below)

  ; The rows above the last are full: '-- More --', then a new page
  LDX ANSI_ROW
  CPX SCREEN_ROWS
  BCC .row_free
  JSR marks_more
  BEQ .marks_done        ; q: the list ends here
.row_free:

  ; Print " a" (mark letter)
  JSR ansi_move_cursor
  LDA #' '
  JSR io_write
  LDA BUF_TEMP
  JSR io_write

  ; Print the 1-based line number right-justified in a 7-char field,
  ; then one space
  CLC
  ADCI16 BUF_PTR16, $0001, DEC_VALUE16
  LDA #' '
  JSR io_write
  JSR io_write               ; (io_write keeps A)
  JSR write_decimal_field
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
  CMP #$7F               ; Not printable ASCII: a space ($80-$9F are C1
  BCS .marks_text_space  ; controls to some terminals)
  CMP #' '
  BCS .marks_text_ok
.marks_text_space:
  LDA #' '
.marks_text_ok:
  JSR io_write
  INY
  BNE .marks_text        ; Always taken (limit < 256)
.marks_text_done:
  INC ANSI_ROW

.marks_next:
  INC BUF_TEMP
  LDA BUF_TEMP
  CMP #'z' + 1
  BNE .marks_loop

  LDA ANSI_ROW
  CMP #2
  BNE .marks_wait        ; At least one mark shown
  JSR ansi_move_cursor   ; Row 2, column 1
  PRINT_STR str_no_marks

.marks_wait:
  JSR flush_get_key
.marks_done:
  LDA #RF_FULL
  STA RENDER_FLAG
  RTS

; Show '-- More --' on the last row and wait for a key.  Returns Z=1 for
; q (the list ends); any other key starts a new page (Z=0)
; Clobbers A, X, Y
marks_more:
  LDA #<str_more
  LDX #>str_more
  JSR show_message_ax
  LSR STATUS_HOLD        ; (the list ends in a full redraw: no hold)
  JSR flush_get_key
  EOR #'q'
  BNE marks_page
  RTS

; Clear the screen, print the header, and point ANSI_ROW/COL at row 2
; (Z=0).  Clobbers A, X, Y
marks_page:
  JSR ansi_clear_screen
  PRINT_STR str_marks_header
  LDX #1
  STX ANSI_COL           ; Every row starts at column 1
  INX
  STX ANSI_ROW           ; First mark row (still 2 at the end = none shown)
  RTS

str_marks_header: .asciiz "mark line text"
str_no_marks:     .asciiz "No marks set"
str_more:         .asciiz "-- More --"

; Save the marks in UNDO_DATA_BUF (in the undo record of a char delete
; or of cc: its undo puts them back, mark_restore).  Clobbers A, X
mark_save:
  LDX #51
.loop:
  LDA MARK_TBL,X
  STA UNDO_DATA_BUF,X
  DEX
  BPL .loop
  RTS

; Put back every mark that was set when mark_save saved them, as vim's u
; does (marks set since then, and unset ones, keep where they are now).
; Clobbers A, X
mark_restore:
  LDX #50
.loop:
  LDA UNDO_DATA_BUF + 1,X
  BMI .next                  ; Unset then
  STA MARK_TBL + 1,X
  LDA UNDO_DATA_BUF,X
  STA MARK_TBL,X
.next:
  DEX
  DEX
  BPL .loop
  RTS

; Adjust marks after a char delete took BUF_TEMP16 = n line breaks after
; line A/X = L, joining lines L to L + n into one, as vim does (it
; deletes the lines between and joins the last): the marks of line L
; stay, those of lines L + 1 to L + n - 1 are unset, those of line L + n
; move to line L and the ones below move up n.  (C = 1: mark_adjust_join,
; C = 0: mark_adjust_delete.)  Clobbers: A, X, Y, BUF_SRC16, BUF_DST16,
; MARK_DELTA16
mark_adjust_join:
  SEC
  .byte $24                  ; BIT zp: skip the CLC
; Adjust marks after lines are deleted
; Input: A/X = first deleted line (16-bit low/high)
;        BUF_TEMP16 = count of deleted lines (16-bit)
; Marks on [first_line, first_line+count): unset
; Marks >= first_line+count: subtract count
; Clobbers: A, X, Y, BUF_SRC16, BUF_DST16, MARK_DELTA16
mark_adjust_delete:
  CLC
  PHP
  STAX16 BUF_SRC16
  CLC
  ADC16 BUF_SRC16, BUF_TEMP16, BUF_DST16   ; end_line = first + count
  SEC
  SBC16 BUF_SRC16, BUF_DST16, MARK_DELTA16 ; delta = -count
  PLP
  BCC .range
  INC16 BUF_SRC16            ; Join: line L's marks stay
.range:
  JMP mark_adjust_range

; Move the marks of the A (1-255) lines after the cursor line to it,
; and the ones below up A lines, as vim's J does: a join at a time, each
; moving the next line's marks up (mark_join_lines_nt: NORMAL_TEMP = A).
; Clobbers A, X, Y, NORMAL_TEMP, BUF_TEMP16, BUF_SRC16, BUF_DST16,
; MARK_DELTA16
mark_join_lines:
  STA NORMAL_TEMP
mark_join_lines_nt:
  JSR set_buf_temp16_one
  LDAX16 FILE_LINE16
  JSR mark_adjust_join
  DEC NORMAL_TEMP
  BNE mark_join_lines_nt
  RTS

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
; A/X = FILE_LINE16 + 1.  Clobbers: A, X
next_line_ax:
  LDX FILE_LINE16 + 1
  LDA FILE_LINE16
  CLC
  ADC #1
  BCC .done
  INX
.done:
  RTS
