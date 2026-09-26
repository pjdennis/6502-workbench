; Search mode handler
;
; Handles '/' command for forward search in the text buffer.
; Pattern is stored in SEARCH_BUF for reuse with 'n' command.
;
; Memory layout:
;   SEARCH_BUF   ($DF54) - Search pattern buffer (after MARK_TBL)
;   SEARCH_LIMIT ($E000) - One past last byte of search buffer
;   SEARCH_MAX   (172)   - Maximum pattern length (SEARCH_LIMIT - SEARCH_BUF)

SEARCH_BUF   = $D654
SEARCH_LIMIT = $D700
SEARCH_MAX   = SEARCH_LIMIT - SEARCH_BUF

  .zeropage

SEARCH_LEN:   .byte     ; Length of current search pattern
SEARCH_IDX:   .byte     ; Current index during search input
SEARCH_LINE16: .word    ; Line number being searched
SEARCH_COL:   .byte     ; Column position of match / start column for search
SEARCH_DIR:   .byte     ; Search direction: 0=forward (/), 1=backward (?)
SEARCH_LIMIT_COL: .byte ; Column limit for backward line search

  .code

; Handle '/' search command
search_handle:
  LDA #'/'
  JMP search_input_handle

; Handle '?' backward search command
search_backward_handle:
  LDA #'?'
  ; Fall through

; Unified search input handler
; A = prompt character ('/' or '?')
search_input_handle:
  STA BUF_TEMP           ; Save prompt char
  LDA #0
  STA SEARCH_IDX

  ; Show prompt on status line
  LDA BUF_TEMP
  JSR show_prompt

.read_loop:
  JSR get_key

  CMP #KEY_ESC
  BEQ .cancel
  CMP #KEY_ENTER
  BEQ .execute
  CMP #KEY_BS
  BEQ .backspace             ; ($7F arrives as KEY_BS)

  ; Printable character?
  CMP #' '
  BCC .read_loop
  CMP #$7F
  BCS .read_loop

  ; Add to buffer
  LDX SEARCH_IDX
  CPX #SEARCH_MAX
  BCS .read_loop   ; Buffer full
  STA SEARCH_BUF,X
  INC SEARCH_IDX

  ; Echo character
  JSR io_write
  JSR io_flush
  JMP .read_loop

.backspace:
  LDA SEARCH_IDX
  BEQ .cancel       ; Nothing to delete, cancel
  DEC SEARCH_IDX
  JSR erase_char
  JMP .read_loop

.cancel:
  RTS

.execute:
  ; If empty search, reuse previous pattern
  LDA SEARCH_IDX
  BEQ .reuse_pattern
  ; Update search length
  STA SEARCH_LEN
  JMP .do_search

.reuse_pattern:
  ; Check if there's a previous pattern
  LDA SEARCH_LEN
  BEQ .cancel       ; No previous pattern either

.do_search:
  ; Set direction based on prompt char
  LDA BUF_TEMP
  CMP #'?'
  BNE .forward
  LDA #1
  STA SEARCH_DIR
  JMP search_backward
.forward:
  LDA #0
  STA SEARCH_DIR
  JMP search_forward

; Search forward from current position
; First searches current line from CURSOR_COL+1, then subsequent lines from col 0
; Wraps around, finally checks current line from col 0
; Sets cursor to matching line/col on success
; Shows "Pattern not found" on failure
search_forward:
  CP16 FILE_LINE16, SEARCH_LINE16

  ; Try current line from CURSOR_COL + 1
  LDA CURSOR_COL16 + 1
  BNE .skip_current          ; CURSOR_COL > 255, skip current line
  LDA CURSOR_COL16
  CLC
  ADC #1
  BCS .skip_current          ; CURSOR_COL = 255, overflow
  STA SEARCH_COL
  JSR search_setup_line
  JSR search_match_from
  BCC .found

.skip_current:
  ; Advance to next line
  CLC
  ADCI16 FILE_LINE16, $0001, SEARCH_LINE16

.line_loop:
  ; Wrap around if past end
  CMP16 SEARCH_LINE16, LINE_COUNT16
  BCC .no_wrap
  SET16 $0000, SEARCH_LINE16
.no_wrap:

  ; Check if we've wrapped all the way back to start line
  CMP16 SEARCH_LINE16, FILE_LINE16
  BEQ .check_current

  ; Search this line from col 0
  JSR search_in_line
  BCC .found

  ; Next line
  INC16 SEARCH_LINE16
  JMP .line_loop

.check_current:
  ; Wrapped back: search current line from col 0 (catches matches at/before cursor)
  JSR search_in_line
  BCC .found

  ; Not found
  JMP search_show_not_found

.found:
  JMP search_move_to_match

; Search backward from current position
; First finds rightmost match before CURSOR_COL on current line
; Then searches previous lines (rightmost match per line)
; Wraps around, finally checks current line for any rightmost match
; Sets cursor to matching line/col on success
; Shows "Pattern not found" on failure
search_backward:
  CP16 FILE_LINE16, SEARCH_LINE16

  ; Try current line: find rightmost match before CURSOR_COL
  LDA CURSOR_COL16 + 1
  BNE .search_whole_current  ; CURSOR_COL > 255, search whole line
  LDA CURSOR_COL16
  BEQ .skip_current          ; CURSOR_COL = 0, nothing before cursor
  STA SEARCH_COL             ; SEARCH_COL = exclusive upper bound
  JSR search_in_line_last
  BCC .found
  JMP .skip_current

.search_whole_current:
  ; CURSOR_COL > 255, search entire current line for rightmost
  JSR search_in_line_last_all
  BCC .found

.skip_current:
  ; Move to previous line (SEARCH_LINE16 still == FILE_LINE16 here,
  ; copied at routine entry and untouched since)
  TST16 FILE_LINE16
  BEQ .wrap                    ; At line 0, wrap to last line
  DEC16 SEARCH_LINE16

.loop:
  ; Check if we've wrapped all the way back to start line
  CMP16 SEARCH_LINE16, FILE_LINE16
  BEQ .check_current

  ; Search this line for rightmost match
  JSR search_in_line_last_all
  BCC .found

  ; Previous line
  TST16 SEARCH_LINE16
  BEQ .wrap
  DEC16 SEARCH_LINE16
  JMP .loop

.wrap:
  ; At line 0, wrap to last line
  SEC
  SBCI16 LINE_COUNT16, $0001, SEARCH_LINE16
  JMP .loop

.check_current:
  ; Wrapped back: search entire current line for rightmost match
  JSR search_in_line_last_all
  BCC .found

  ; Not found
  JMP search_show_not_found

.found:
  JMP search_move_to_match

; Move cursor to search match position
; SEARCH_LINE16 = line of match, SEARCH_COL = column of match
search_move_to_match:
  CP16 SEARCH_LINE16, FILE_LINE16
  LDA SEARCH_COL
  STA CURSOR_COL16
  LDA #0
  STA CURSOR_COL16 + 1
  JMP clamp_cursor_col

; Search for pattern in line SEARCH_LINE16 starting from column 0
; Returns carry clear = found (SEARCH_COL set), carry set = not found
search_in_line:
  LDA #0
  STA SEARCH_COL
  JSR search_setup_line
  JMP search_match_from

; Set up BUF_PTR16 for line SEARCH_LINE16
search_setup_line:
  LDAX16 SEARCH_LINE16
  JMP buf_get_line_ptr       ; BUF_PTR16 = start of line

; Search for pattern starting from column SEARCH_COL
; BUF_PTR16 must already point to line start (call search_setup_line first)
; Returns carry clear = found (SEARCH_COL set), carry set = not found
; Clobbers: A, X, Y
search_match_from:
  ; Outer loop: try each starting position in the line
  LDY SEARCH_COL             ; Y = start position in line
.outer_loop:
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .not_found_in_line     ; Reached end of line

  ; Inner loop: compare pattern starting at position Y
  STY SEARCH_COL             ; Save potential match start
  LDX #0                     ; X = pattern index
.inner_loop:
  CPX SEARCH_LEN
  BEQ .found_in_line         ; Matched entire pattern

  ; Compute line offset: Y = SEARCH_COL + X
  TXA
  CLC
  ADC SEARCH_COL
  BCS .not_found_here        ; Sum > 255, can't index with Y
  TAY

  ; Check for end of line
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .not_found_here        ; Hit end of line during match

  ; Compare with pattern char (X still = pattern index)
  CMP SEARCH_BUF,X
  BNE .not_found_here

  INX                        ; Next pattern char
  JMP .inner_loop

.not_found_here:
  LDY SEARCH_COL
  INY                        ; Try next start position
  BEQ .not_found_in_line     ; Y wrapped past 255
  JMP .outer_loop

.found_in_line:
  ; SEARCH_COL already set to match position
  CLC
  RTS

.not_found_in_line:
  SEC
  RTS

; Entry with no upper bound: search the entire line for the rightmost match
search_in_line_last_all:
  LDA #0
  STA SEARCH_COL
  ; fall through

; Find the rightmost match in line SEARCH_LINE16
; Input: SEARCH_COL = exclusive upper bound column (0 = search entire line)
; Returns carry clear = found (SEARCH_COL set to rightmost match), carry set = not found
; Uses BUF_DELTA as "best match found" tracker ($FF = none)
search_in_line_last:
  LDA SEARCH_COL
  STA SEARCH_LIMIT_COL       ; Save limit
  LDA #$FF
  STA BUF_DELTA              ; No match found yet
  LDA #0
  STA SEARCH_COL             ; Start searching from col 0
  JSR search_setup_line

.loop:
  JSR search_match_from
  BCS .done                  ; No more matches

  ; Check if match is past limit (when limit > 0)
  LDA SEARCH_LIMIT_COL
  BEQ .save                  ; 0 = no limit, accept any match
  LDA SEARCH_COL
  CMP SEARCH_LIMIT_COL
  BCS .done                  ; Match at/past limit, stop

.save:
  ; Save this match position, continue looking
  LDA SEARCH_COL
  STA BUF_DELTA
  CLC
  ADC #1
  BCS .done                  ; Can't advance past 255
  STA SEARCH_COL
  JMP .loop

.done:
  ; Return best match found
  LDA BUF_DELTA
  CMP #$FF
  BEQ .not_found
  STA SEARCH_COL
  CLC
  RTS
.not_found:
  SEC
  RTS

; Show "Pattern not found: <pattern>" on status line
search_show_not_found:
  JSR status_line_clear
  PRINT_STR str_not_found

  ; Print the pattern
  LDX #0
.print_pattern:
  CPX SEARCH_LEN
  BEQ .print_done
  LDA SEARCH_BUF,X
  JSR io_write
  INX
  JMP .print_pattern
.print_done:
  JMP flush_get_key            ; Wait for keypress

; String constants
str_not_found: .asciiz "Pattern not found: "
