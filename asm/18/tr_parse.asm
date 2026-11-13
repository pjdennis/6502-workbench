; tr_parse.asm - Hex parser, decimal parser, and line reader


; ============================================================================
; HEX PARSER
; ============================================================================

; Parse hex byte pairs from TR_LINE_BUF into TR_EXPECT_BUF
; On entry: Y = offset in TR_LINE_BUF
; On exit: TR_EXPECT_LEN16 updated
tr_parse_hex_from_buf:
.loop:
  CPY TR_LINE_LEN
  BCS .done
  LDA TR_LINE_BUF,Y
  CMP #' '
  BNE .hex_hi
  INY
  JMP .loop
.hex_hi:
  JSR tr_hex_char_to_val
  BCS .done
  ASL
  ASL
  ASL
  ASL
  STA TR_TEMP                ; High nibble
  INY
  CPY TR_LINE_LEN
  BCS .done
  LDA TR_LINE_BUF,Y
  JSR tr_hex_char_to_val
  BCS .done
  ORA TR_TEMP                ; Combine nibbles
  JSR tr_store_expect_byte
  INY
  JMP .loop
.done:
  RTS

; Continue parsing hex bytes directly from the file (for truncated lines)
; Reads chars until newline or EOF
tr_parse_hex_from_file:
  LDA #$00
  STA TR_TEMP                ; State: 0=need hi, 1=need lo
.loop:
  LDA TR_FILE_HANDLE
  JSR read
  BCS .done
  CMP #$0A
  BEQ .done
  CMP #' '
  BEQ .loop               ; Skip spaces
  JSR tr_hex_char_to_val
  BCS .loop               ; Skip non-hex
  LDX TR_TEMP
  BNE .lo_nibble
  ; High nibble
  ASL
  ASL
  ASL
  ASL
  STA TR_SCRATCH16                ; Temp store high nibble
  LDA #$01
  STA TR_TEMP
  JMP .loop
.lo_nibble:
  ORA TR_SCRATCH16
  JSR tr_store_expect_byte
  LDA #$00
  STA TR_TEMP
  JMP .loop
.done:
  LDA #$00
  STA TR_LINE_TRUNC
  RTS

; Store a byte in TR_EXPECT_BUF and increment TR_EXPECT_LEN16
; On entry: A = byte to store
; Preserves Y (caller uses Y as buffer index)
; Fails fast if buffer would overflow (512 byte limit)
tr_store_expect_byte:
  STY tr_store_save_y       ; Save caller's Y
  PHA
  ; Check for buffer overflow (512 bytes max)
  CMPI16 TR_EXPECT_LEN16, $0200
  BCC .ok
  JMP tr_err_expect_overflow
.ok:
  ; Use 16-bit index for >256 byte buffers
  LDAX16 TR_EXPECT_LEN16
  STX TR_PTR16 + 1
  CLC
  ADC #<TR_EXPECT_BUF
  STA TR_PTR16
  LDA TR_PTR16 + 1
  ADC #>TR_EXPECT_BUF
  STA TR_PTR16 + 1
  PLA
  LDY #$00
  STA (TR_PTR16),Y
  INC16 TR_EXPECT_LEN16
  LDY tr_store_save_y       ; Restore caller's Y
  RTS

tr_store_save_y: .byte 0

; Convert ASCII hex char in A to value 0-15
; On exit: A = value, C clear = valid, C set = invalid
tr_hex_char_to_val:
  CMP #'0'
  BCC .invalid
  CMP #':'                ; '9' + 1
  BCC .digit
  CMP #'a'
  BCC .invalid
  CMP #'g'                ; 'f' + 1
  BCS .invalid
  SEC
  SBC #'a'-$0A
  CLC
  RTS
.digit:
  SEC
  SBC #'0'
  CLC
  RTS
.invalid:
  SEC
  RTS


; ============================================================================
; DECIMAL PARSER
; ============================================================================

; Parse decimal number from TR_LINE_BUF starting at offset Y
; Result stored in TR_PARSE16 (16-bit)
; On exit: Y = past last digit, TR_PARSE16 = parsed value
tr_parse_decimal:
  LDA #$00
  STA TR_PARSE16
  STA TR_PARSE16 + 1
.loop:
  CPY TR_LINE_LEN
  BCS .done
  LDA TR_LINE_BUF,Y
  CMP #'0'
  BCC .done
  CMP #':'                ; '9' + 1
  BCS .done
  SEC
  SBC #'0'
  STA TR_TEMP                ; Save digit
  ; TR_PARSE16 *= 10 = (x*4 + x) * 2
  CP16 TR_PARSE16, TR_SCRATCH16        ; saved x
  ASL16 TR_PARSE16             ; x*2
  ASL16 TR_PARSE16             ; x*4
  CLC
  ADC16 TR_PARSE16, TR_SCRATCH16, TR_PARSE16  ; x*4 + x = x*5
  ASL16 TR_PARSE16             ; x*10
  ; Add digit
  LDA TR_TEMP
  CLC
  ADC TR_PARSE16
  STA TR_PARSE16
  BCC .no_carry
  INC TR_PARSE16 + 1
.no_carry:
  INY
  JMP .loop
.done:
  RTS


; ============================================================================
; LINE READER
; ============================================================================

; Read one line from the test file into TR_LINE_BUF
; On exit: TR_LINE_LEN = length (excluding newline)
;          TR_LINE_TRUNC = 1 if line was truncated (more data in file)
;          C clear = line read OK (or truncated)
;          C set = EOF reached (TR_LINE_LEN may be >0 for partial line)
;          A, X, Y not preserved
tr_read_line:
  LDY #$00              ; Buffer index
.loop:
  CPY #$FF              ; Buffer full? Check BEFORE reading
  BCS .full
  LDA TR_FILE_HANDLE
  JSR read              ; Read char; C set at EOF
  BCS .eof
  CMP #$0A              ; Newline?
  BEQ .eol
  STA TR_LINE_BUF,Y
  INY
  JMP .loop
.full:
  STY TR_LINE_LEN       ; 255 chars stored
  LDA #$01
  STA TR_LINE_TRUNC     ; More data in file for this line
  CLC
  RTS
.eol:
  STY TR_LINE_LEN
  LDA #$00
  STA TR_LINE_TRUNC
  CLC                   ; Line read OK
  RTS
.eof:
  STY TR_LINE_LEN
  LDA #$00
  STA TR_LINE_TRUNC
  SEC                   ; EOF
  RTS

; Skip remaining chars on current line (when truncated)
; Reads from file until newline or EOF
tr_skip_rest_of_line:
  LDA TR_LINE_TRUNC
  BEQ .done
.loop:
  LDA TR_FILE_HANDLE
  JSR read
  BCS .eof
  CMP #$0A
  BNE .loop
.eof:
  LDA #$00
  STA TR_LINE_TRUNC
.done:
  RTS
