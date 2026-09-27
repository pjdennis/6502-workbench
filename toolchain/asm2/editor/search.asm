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

search_ret:
  RTS

; Read a pattern at the '/' or '?' prompt (A = the prompt character) and
; search for it
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
  ; fall through

; Search in direction A (0 = forward, $10 = backward; Z set from it)
search_dir:
  BNE search_backward
  ; fall through

; Search forward from current position
; First searches current line after the cursor, then subsequent lines from col 0
; Wraps around, finally checks current line from col 0
; Sets cursor to matching line/col on success
; Shows "Pattern not found" on failure
search_forward:
  CP16 FILE_LINE16, SEARCH_LINE16

  ; Try the current line: its first match (of those search_line_walk
  ; steps through) that starts after the cursor
  JSR get_current_line_ptr
  SEC
  ADC16 CURSOR_COL16, BUF_PTR16, SEARCH_LIMIT16 ; The cursor's address + 1
  JSR search_line_walk
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

; Move the cursor to the match at BUF_PTR16 on line SEARCH_LINE16 (a
; match always starts inside the line, so no clamp is needed)
search_move_to_match:
  CP16 SEARCH_LINE16, FILE_LINE16
  CP16 BUF_PTR16, CURSOR_COL16 ; Match address
  JSR get_current_line_ptr     ; BUF_PTR16 = line start
  SEC
  SBC16 CURSOR_COL16, BUF_PTR16, CURSOR_COL16
  RTS

; Search backward from current position
; First finds rightmost match before the cursor on current line
; Then searches previous lines (rightmost match per line)
; Wraps around, finally checks current line for any rightmost match
; Sets cursor to matching line/col on success
; Shows "Pattern not found" on failure
search_backward:
  CP16 FILE_LINE16, SEARCH_LINE16

  ; Try current line: the last match that starts before the cursor
  JSR get_cursor_buf_ptr
  CP16 BUF_PTR16, SEARCH_LIMIT16
  JSR search_in_line_last
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
; Returns carry clear = found (BUF_PTR16 = match), carry set = not found
search_in_line:
  JSR search_setup_line
  ; fall through

; Find the first match at or after BUF_PTR16 on its line.  Columns are
; 16-bit: the pointer walks the line, Y indexes the pattern
; Returns carry clear = found (BUF_PTR16 = match start), carry set = none
; Clobbers: A, Y
search_match_from:
  LDY #0
  LDA (BUF_PTR16),Y
  CMP SEARCH_BUF             ; Quick first-char test
  BEQ .try
  CMP #'\n'
  BEQ .none                  ; End of line (carry set)
.advance:
  INC BUF_PTR16
  BNE search_match_from
  INC BUF_PTR16 + 1
  BNE search_match_from      ; Always taken
.try:
  INY
  CPY SEARCH_LEN
  BEQ .hit
  LDA (BUF_PTR16),Y          ; A '\n' never equals a (printable) pattern
  CMP SEARCH_BUF,Y           ; char, so the line end fails the compare
  BEQ .try
  BNE .advance               ; Always taken
.hit:
  CLC
.none:
  RTS

; Set up BUF_PTR16 for line SEARCH_LINE16
search_setup_line:
  LDAX16 SEARCH_LINE16
  JMP buf_get_line_ptr       ; BUF_PTR16 = start of line

; Entry with no upper bound: search the entire line for its last match
search_in_line_last_all:
  LDA #$FF
  STA_LH16 SEARCH_LIMIT16
  ; fall through

; Find the last match (of those search_line_walk steps through) in line
; SEARCH_LINE16 that starts before address SEARCH_LIMIT16
; Returns carry clear = found (BUF_PTR16 = match), carry set = not found
search_in_line_last:
  JSR search_line_walk
  CP16 BUF_DST16, BUF_PTR16
  LDA #0
  CMP BUF_DST16 + 1          ; Carry clear = a match was saved
  RTS

; Step through the matches of line SEARCH_LINE16 as vi does, each search
; going on from the end of the match before (vim's 'cpoptions' c: the
; matches do not overlap), up to the first one that starts at or after
; address SEARCH_LIMIT16.
; Returns carry clear = found (BUF_PTR16 = that match), carry set = none;
; either way BUF_DST16 = the last match before it (high byte 0 = none:
; the text never lives in page zero)
search_line_walk:
  LDA #0
  STA BUF_DST16 + 1
  JSR search_setup_line
.loop:
  JSR search_match_from
  BCS .done                  ; No more matches
  CMP16 BUF_PTR16, SEARCH_LIMIT16
  BCS .at_limit              ; Match at/past limit
  CP16 BUF_PTR16, BUF_DST16  ; The last one before the limit so far
  LDA SEARCH_LEN
  ADDA16 BUF_PTR16           ; Go on from the end of the match
  JMP .loop
.at_limit:
  CLC
.done:
  RTS

; String constants
str_not_found: .asciiz "Pattern not found: "
