; Search mode handler
;
; Handles '/' (forward) and '?' (backward) literal search in the text
; buffer. The pattern is read into CMD_BUF by read_line (up to 127
; characters, as a ':' command) and copied to SEARCH_BUF (length
; SEARCH_LEN) on a non-empty Enter, for reuse by 'n' / 'N' and by an
; empty '/' or '?': a cancelled search keeps the pattern, as in vim.
;
; Memory layout:
;   SEARCH_BUF   ($D654) - Search pattern buffer (after MARK_TBL; 127 of
;                          its 172 bytes are used)

SEARCH_BUF   = $D654

; (zero-page variables: zp.asm)

; Handle '/' search command
search_handle:
  LDA #'/'
  BNE search_input_handle ; Always taken
search_ret:
  RTS

; Handle '?' backward search command
search_backward_handle:
  LDA #'?'
  ; Fall through

; Unified search input handler
; A = prompt character ('/' or '?')
search_input_handle:
  STA BUF_TEMP           ; Save prompt char
  JSR read_line          ; X = length
  BCS search_ret         ; Cancelled

  ; Empty input reuses the previous pattern
  TXA
  BEQ .reuse_pattern
  STX SEARCH_LEN
.copy:
  LDA CMD_BUF - 1,X
  STA SEARCH_BUF - 1,X
  DEX
  BNE .copy

.reuse_pattern:
  ; Check if there's a pattern (always true after a copy)
  LDA SEARCH_LEN
  BEQ search_ret         ; No previous pattern either

  ; Direction from the prompt char: 0 = forward (/), $10 = backward (?)
  LDA BUF_TEMP
  EOR #'/'
  STA SEARCH_DIR
  BNE search_backward
  ; fall through

; Search forward from current position
; First searches current line from CURSOR_COL+1, then subsequent lines from col 0
; Wraps around, finally checks current line from col 0
; Sets cursor to matching line/col on success
; Shows "Pattern not found" on failure
search_forward:
  CP16 FILE_LINE16, SEARCH_LINE16

  ; Try current line from CURSOR_COL + 1
  LDA CURSOR_COL16 + 1
  BNE .line_loop             ; CURSOR_COL > 255, skip current line
  LDA CURSOR_COL16
  CLC
  ADC #1
  BCS .line_loop             ; CURSOR_COL = 255, overflow
  STA SEARCH_COL
  JSR search_setup_line
  JSR search_match_from
  BCC search_move_to_match

.line_loop:
  ; Next line (SEARCH_LINE16 = FILE_LINE16 the first time), wrapping
  ; around past the end
  INC16 SEARCH_LINE16
  CMP16 SEARCH_LINE16, LINE_COUNT16
  BCC .no_wrap
  LDA #0
  STA_LH16 SEARCH_LINE16
.no_wrap:

  ; Search this line from col 0
  JSR search_in_line
  BCC search_move_to_match

  ; Stop once the start line itself has been searched from col 0
  ; (catches matches at/before the cursor)
  CMP16 SEARCH_LINE16, FILE_LINE16
  BNE .line_loop
  JMP search_show_not_found

; Move cursor to search match position
; SEARCH_LINE16 = line of match, SEARCH_COL = column of match
search_move_to_match:
  CP16 SEARCH_LINE16, FILE_LINE16
  LDA SEARCH_COL
  STA CURSOR_COL16
  LDA #0
  STA CURSOR_COL16 + 1
  JMP clamp_cursor_col

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
  BEQ .line_loop             ; CURSOR_COL = 0, nothing before cursor
  STA SEARCH_COL             ; SEARCH_COL = exclusive upper bound
  JSR search_in_line_last
  BCC search_move_to_match
  BCS .line_loop             ; Always taken

.search_whole_current:
  ; CURSOR_COL > 255, search entire current line for rightmost
  JSR search_in_line_last_all
  BCC search_move_to_match

.line_loop:
  ; Previous line (SEARCH_LINE16 = FILE_LINE16 the first time), wrapping
  ; around from line 0 to the last line
  TST16 SEARCH_LINE16
  BNE .no_wrap
  CP16 LINE_COUNT16, SEARCH_LINE16
.no_wrap:
  DEC16 SEARCH_LINE16

  ; Search this line for rightmost match
  JSR search_in_line_last_all
  BCC search_move_to_match

  ; Stop once the start line itself has been searched in full
  CMP16 SEARCH_LINE16, FILE_LINE16
  BNE .line_loop
  ; Not found: fall through

; Show "Pattern not found: <pattern>" on status line
search_show_not_found:
  JSR status_line_clear
  PRINT_TEXT str_not_found

  ; Print the pattern
  LDX #0
.print_pattern:
  CPX SEARCH_LEN
  BEQ .print_done
  LDA SEARCH_BUF,X
  JSR text_putc              ; (preserves X)
  INX
  BNE .print_pattern         ; Always taken (SEARCH_LEN <= 127)
.print_done:
  JMP flush_get_key            ; Wait for keypress

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

; String constants
str_not_found: .asciiz "Pattern not found: "
