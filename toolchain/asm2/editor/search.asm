; Search mode handler
;
; Handles '/' (forward) and '?' (backward) literal search in the text
; buffer. The pattern is read into CMD_BUF by read_line (up to 127
; characters, as a ':' command) and copied to SEARCH_BUF (null-terminated;
; its length in SEARCH_LEN) on a non-empty Enter, for reuse by 'n' / 'N'
; and by an empty '/' or '?': a cancelled search keeps the pattern, as in
; vim.
;
; Memory layout:
;   SEARCH_BUF   ($D654) - Search pattern buffer (after MARK_TBL; 127 of
;                          its 172 bytes are used)

SEARCH_BUF   = $D654

; (zero-page variables: zp.asm)

; Read a pattern at the '/' or '?' prompt (A = the prompt character):
; the search pattern (an empty one keeps the previous pattern, if any)
; and its direction.  Returns carry set if cancelled
search_input_handle:
  STA BUF_TEMP           ; Save prompt char
  JSR read_line          ; X = length
  BCS .ret               ; Cancelled

  ; Empty input reuses the previous pattern
  TXA
  BEQ .reuse_pattern
  STX SEARCH_LEN
.copy:
  LDA CMD_BUF,X              ; (from the null terminator down)
  STA SEARCH_BUF,X
  DEX
  BPL .copy

.reuse_pattern:
  ; Direction from the prompt char: 0 = forward (/), $10 = backward (?)
  LDA BUF_TEMP
  EOR #'/'
  STA SEARCH_DIR
.ret:
  RTS                        ; (C = 0 from read_line)

; Search in direction A (0 = forward, $10 = backward; Z set from it).
; Returns carry set if found, clear if not
search_dir:
  BNE search_backward
  ; fall through

; Search forward from current position
; First searches current line after the cursor, then subsequent lines from col 0
; Wraps around, finally checks current line from col 0
; Sets cursor to matching line/col on success
; Shows "Pattern not found" on failure
search_forward:
  ; Try the current line: its first match (of those search_line_walk
  ; steps through) that starts after the cursor
  JSR search_start
  INC16 SEARCH_LIMIT16         ; The cursor's address + 1
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
; match always starts inside the line, so no clamp is needed).  Returns
; carry set (the column is not negative)
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
  ; Try current line: the last match that starts before the cursor
  JSR search_start
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

; Show "Pattern not found: <pattern>" on status line; returns carry
; clear
search_show_not_found:
  JSR status_line_clear
  PRINT_TEXT str_not_found

  PRINT_TEXT SEARCH_BUF
  JSR flush_get_key            ; Wait for keypress
  CLC
  RTS

; Start a search on the cursor line: SEARCH_LINE16 = FILE_LINE16 and
; SEARCH_LIMIT16 = the cursor's address
search_start:
  CP16 FILE_LINE16, SEARCH_LINE16
  JSR get_cursor_buf_ptr
  CP16 BUF_PTR16, SEARCH_LIMIT16
  RTS

; Search for pattern in line SEARCH_LINE16 starting from column 0
; Returns carry clear = found (BUF_PTR16 = match), carry set = not found
search_in_line:
  JSR search_setup_line
  ; fall through

; Find the first match at or after BUF_PTR16 on its line.  Columns are
; 16-bit: the pointer walks the line, Y indexes the pattern
; Returns carry clear = found (BUF_PTR16 = match start, Y = the pattern's
; length), carry set = none
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
  LDA SEARCH_BUF,Y
  BEQ .hit                   ; The pattern's null terminator
  CMP (BUF_PTR16),Y          ; A '\n' never equals a (printable) pattern
  BEQ .try                   ; char, so the line end fails the compare
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
  TYA                        ; The pattern's length
  ADDA16 BUF_PTR16           ; Go on from the end of the match
  JMP .loop
.at_limit:
  CLC
.done:
  RTS

; String constants
str_not_found: .asciiz "Pattern not found: "
