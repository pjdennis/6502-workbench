read     = $F006 ; Provided by emulation environment
write_b  = $F009 ; Provided by emulation environment

TEMP     = $0000 ; 1 byte
NEXTCHAR = $0001 ; 1 byte
TABL     = $0002 ; 1 byte
TABH     = $0003 ; 1 byte
PCL      = $0004 ; 1 byte
PCH      = $0005 ; 1 byte
HEX1     = $0006 ; 1 byte
HEX2     = $0007 ; 1 byte
PASS     = $0008 ; 1 byte $00 = pass1 $FF = pass2
TOKEN    = $0009 ; multiple bytes

LBTAB    = $3000

*        = $2000 ; .org $2000


; Emulation environment surfaces error codes and messages
err_labelnotfound
  BRK $01 "Label not found" $00

err_duplicatelabel
  BRK $02 "Duplicate label" $00

err_opcodenotfound
  BRK $03 "Opcode not found" $00

err_expectedhex
  BRK $04 "Expected hex value" $00


; Instruction table
MNTAB
;      Mnemonic           Opcode
  DATA "ADC#"     $00 $00 $69
  DATA "ADCZ"     $00 $00 $65
  DATA "AND#"     $00 $00 $29
  DATA "ASLA"     $00 $00 $0A
  DATA "BCC"      $00 $00 $90
  DATA "BCS"      $00 $00 $B0
  DATA "BEQ"      $00 $00 $F0
  DATA "BITZ"     $00 $00 $24
  DATA "BMI"      $00 $00 $30
  DATA "BNE"      $00 $00 $D0
  DATA "BPL"      $00 $00 $10
  DATA "BRK"      $00 $00 $00
  DATA "CLC"      $00 $00 $18
  DATA "CMP#"     $00 $00 $C9
  DATA "CMP,Y"    $00 $00 $D9
  DATA "EORZ"     $00 $00 $45
  DATA "INCZ"     $00 $00 $E6
  DATA "INX"      $00 $00 $E8
  DATA "INY"      $00 $00 $C8
  DATA "JMP"      $00 $00 $4C
  DATA "JSR"      $00 $00 $20
  DATA "LDA#"     $00 $00 $A9
  DATA "LDAZ(),Y" $00 $00 $B1
  DATA "LDA,X"    $00 $00 $BD
  DATA "LDA,Y"    $00 $00 $B9
  DATA "LDAZ"     $00 $00 $A5
  DATA "LDAZ,X"   $00 $00 $B5
  DATA "LDX#"     $00 $00 $A2
  DATA "LDY#"     $00 $00 $A0
  DATA "LSRA"     $00 $00 $4A
  DATA "ORAZ"     $00 $00 $05
  DATA "PHA"      $00 $00 $48
  DATA "PLA"      $00 $00 $68
  DATA "RTS"      $00 $00 $60
  DATA "SBC#"     $00 $00 $E9
  DATA "SBCZ"     $00 $00 $E5
  DATA "SEC"      $00 $00 $38
  DATA "STA"      $00 $00 $8D
  DATA "STAZ(),Y" $00 $00 $91
  DATA "STA,X"    $00 $00 $9D
  DATA "STA,Y"    $00 $00 $99
  DATA "STAZ"     $00 $00 $85
  DATA "STAZ,X"   $00 $00 $95
  DATA "TAY"      $00 $00 $A8
  DATA "TYA"      $00 $00 $98
  DATA "DATA"     $00 $01 $00 ; Directive
  DATA $00


emit
  BITZ <PASS
  BPL $03              ; BVC emit_incpc
  JSR write_b
emit_incpc
  INCZ <PCL
  BNE $02              ; BNE emit_done
  INCZ <PCH
emit_done
  RTS


skiprestofline
  CMP# "\n"
  BEQ $06              ; BNE srol_done
  JSR read
  JMP skiprestofline
srol_done
  RTS


skipspaces
  CMP# " "
  BNE $06              ; BNE ss_done
  JSR read
  JMP skipspaces
ss_done
  RTS


cmpendoftoken
  CMP# " "
  BNE $01
  RTS
  CMP# "\n"
  BNE $01
  RTS
  CMP# ";"
  RTS


; Checks for end of line and skips past if at end
; On entry A contains next character
; On exit C set if end of line, clear otherwise
;         A contains next character
checkforend
  CMP# ";"
  BEQ $06              ; BEQ cfe_end
  CMP# "\n"
  BEQ $02              ; BEQ cfe_end
  ; Not at end
  CLC
  RTS
cfe_end
  JSR skiprestofline
  SEC
  RTS


; On entry A contains first character of token
; Reads token into TOKEN (zero terminated)
; On exit NEXTCHAR contains next character after token
;         Y is preserved
;         A, X are not preserved
readtoken
  LDX# $00
readtokenloop
  STAZ,X <TOKEN
  INX
  JSR read
  JSR cmpendoftoken
  BEQ $03              ; BEQ rt_done
  JMP readtokenloop
rt_done
  STAZ <NEXTCHAR
  LDA# $00
  STAZ,X <TOKEN
  RTS


; On entry Y contains offset into TAB
; On exit TABL;TABH += Y + 1
;         Y = 0
;         A is not preserved
advanceintab
  INY
  TYA
  LDY# $00
  CLC
  ADCZ <TABL
  STAZ <TABL
  TYA                  ; A <- 0
  ADCZ <TABH
  STAZ <TABH
  RTS


; On entry TOKEN contains token to find
;          TABL;TABH points to table
; On exit C clear if found; set if not found
;         TABL;TABH points to token value if found
;                   or to end of table if not found
;         Y = 0
;         A is not preserved
findintab
  LDY# $00
fit_tokenloop          ; Outer loop
  LDA(),Y <TABL
  BNE $02              ; BNE fit_charloop
  ; not found
  SEC
  RTS
;invariant: pointed at first char
; first char of mnenomic in table loaded
fit_charloop           ; inner loop
  CMP,Y TOKEN
  BNE $0F              ; BNE fit_skipcurrent ; not a match
  CMP# $00
  BNE $05              ; BNE fit_nextchar ; partial match so far
  ; found a match
  JSR advanceintab
  CLC
  RTS
fit_nextchar           ; Move to next char
  INY
  LDA(),Y <TABL
  JMP fit_charloop     ; Inner loop
fit_skipcurrent        ; Skip current symbol in table
  LDA(),Y <TABL
  BEQ $04              ; BEQ fit_nextsymbol ; done skipping
  INY
  JMP fit_skipcurrent
fit_nextsymbol         ; Move to next symbol in table
  INY                  ; Move past 2 data bytes
  INY
  JSR advanceintab
  JMP fit_tokenloop    ; Outer loop


; On entry TOKEN contains a label
; On exit C clear if found; set if not found
;         TABL;TABH points to token value if found
;                   or to end of table if not found
;         Y = 0
;         A is not preserved
findlabel
  LDA# <LBTAB
  STAZ <TABL
  LDA# >LBTAB
  STAZ <TABH
  JMP findintab        ; Tail call


; On exit NEXTCHAR contains the next character
readandfindexistinglabel
  JSR readtoken
  BITZ <PASS
  BMI $08              ; rafel_pass2
  LDA# $00
  STAZ <TABL
  STAZ <TABH
  CLC
  RTS
rafel_pass2
  JSR findlabel
  BCS $01              ; BCS rafel_notfound
  RTS
rafel_notfound
  JMP err_labelnotfound


; On entry, A contains a hex character A-Z|0-9
; On exit A contains the value (0-15)
convhex
  CMP# "A"
  BCC $06              ; BCC ch_numeric ; < 'A'
  SBC# "A"             ; Carry already set
  CLC
  ADC# $0A             ; ADC# 10
  RTS
ch_numeric
  SEC
  SBC# "0"
  RTS


; On entry A contains first hex character
; Reads second hex character; Uses TEMP
; On exit A contains 2 character value (0-255)
readhex
  JSR convhex
  ASLA
  ASLA
  ASLA
  ASLA
  STAZ <TEMP
  JSR read
  JSR convhex
  ORAZ <TEMP
  RTS


; On entry, next character read will be first hex character
; On exit C set if 2 bytes read clear if 1 byte read
;         A contains the next character
grabhex
  JSR read             ; Read the first hex character
  JSR readhex
  STAZ <HEX1
  JSR read
  JSR cmpendoftoken
  BNE $02              ; BNE gh_second
  CLC
  RTS
gh_second
  JSR readhex
  STAZ <HEX2
  JSR read
  SEC
  RTS


; Read 2 to 4 hex characters and emit 1 or 2 bytes
; When 2 bytes, emit LSB then MSB
; Uses HEX1, HEX2 and NEXTCHAR
; On exit A contains next character
emithex
  JSR grabhex
  STAZ <NEXTCHAR
  BCC $05              ; BCC eh_one
  LDAZ <HEX2
  JSR emit
eh_one
  LDAZ <HEX1
  JSR emit
  LDAZ <NEXTCHAR
  RTS

; On entry NEXTCHAR contains the next character
; On exit C set if value read; clear otherwise
readvalue
  LDAZ <NEXTCHAR
  JSR skipspaces
  CMP# "="
  BEQ $02              ; BNE rv_value
  CLC
  RTS
rv_value
  JSR read             ; Read the character after the "="
  JSR skipspaces
  CMP# "$"
  BEQ $03              ; BEQ rv_hexvalue
  JMP err_expectedhex
rv_hexvalue
  JMP grabhex          ; Tail call


; capturelabel helper
cl_setpc
  JSR readvalue
  JSR skiprestofline
  LDAZ <HEX2
  STAZ <PCL
  LDAZ <HEX1
  STAZ <PCH
  RTS

; capturelabel
capturelabel
  JSR readtoken
  LDAZ <TOKEN
  CMP# "*"
  BNE $03              ; BNE cl_normallabel
  JMP cl_setpc
cl_normallabel
  BITZ <PASS
  BPL $05              ; BPL cl_pass1
  LDAZ <NEXTCHAR
  JMP skiprestofline   ; Tail call
cl_pass1
  JSR findlabel
  BCS $03              ; BCS cl_notfound
  JMP err_duplicatelabel
cl_notfound
cl_loop                ; Copy TOKEN to table
  LDA,Y TOKEN
  STA(),Y <TABL
  BEQ $04              ; BEQ cl_copyvalue
  INY
  JMP cl_loop
cl_copyvalue           ; Copy value or PC value to table
  JSR readvalue
  STAZ <NEXTCHAR
  BCS $08              ; BCS cl_hextotable
  ; Store program counter
  LDAZ <PCL
  STAZ <HEX2
  LDAZ <PCH
  STAZ <HEX1
cl_hextotable
  INY
  LDAZ <HEX2
  STA(),Y <TABL
  INY
  LDAZ <HEX1
  STA(),Y <TABL
  ; Skip past rest of table
  LDAZ <NEXTCHAR
  JSR skiprestofline
  ; Terminate table value
  INY
  LDA# $00
  STA(),Y <TABL
  RTS


; Emit the opcode
; On exit A contains the next character
emitopcode
  JSR readtoken
  LDA# <MNTAB
  STAZ <TABL
  LDA# >MNTAB
  STAZ <TABH
  JSR findintab
  BCC $03              ; BCC eo_found
  JMP err_opcodenotfound
eo_found
  LDA(),Y <TABL
  BNE $06              ; BNE eo_done ; Not opcode (DATA command)
  ; Opcode
  INY
  LDA(),Y <TABL
  JSR emit
eo_done
  LDAZ <NEXTCHAR
  RTS


; Read and emit quoted ASCII
emitquoted
  JSR read
  CMP# "\""
  BNE $04              ; BNE eq_notdone
  JSR read             ; Done; read next char
  RTS
eq_notdone
  CMP# "\\"
  BNE $09              ; BNE eq_notescaped
  JSR read
  CMP# "n"
  BNE $02              ; BNE eq_notescaped
  LDA# "\n"            ; Escaped "n" is linefeed
eq_notescaped
  JSR emit
  JMP emitquoted


; On exit A contains the next character
emitlabel
  JSR readandfindexistinglabel
  ; Emit low byte then high byte from table
  LDA(),Y <TABL
  JSR emit
  INY
  LDA(),Y <TABL
  JSR emit
  LDAZ <NEXTCHAR       ; Load next character
  RTS


; On exit A contains the next character
emitlabellsb
  JSR readandfindexistinglabel
  ; Emit low byte
  LDA(),Y <TABL
  JSR emit
  LDAZ <NEXTCHAR       ; Load next character
  RTS


; On exit A contains the next character
emitlabelmsb
  JSR readandfindexistinglabel
  ; Emit high byte
  INY
  LDA(),Y <TABL
  JSR emit
  LDAZ <NEXTCHAR       ; Load next character
  RTS


emitlabelrel
  BITZ <PASS           ; <PASS
  BMI $09              ; BMI elr_pass2
  JSR readtoken
  JSR emit
  LDAZ <NEXTCHAR
  RTS
elr_pass2
  JSR readandfindexistinglabel
  ; Calculate target - PC - 1
  CLC ; for the - 1
  LDA(),Y <TABL
  SBCZ <PCL
  JSR emit
  LDAZ <NEXTCHAR
  RTS


; Main assembler
assemble
lnloop
  JSR read
  BCC $01              ; BCC lnloop1
  RTS                  ; At end of input
lnloop1
  JSR checkforend
  BCC $03              ; BCC lnloop2
  JMP lnloop
lnloop2
  CMP# " "
  BEQ $06              ; BEQ lnloop3
  JSR capturelabel
  JMP lnloop
lnloop3
  JSR skipspaces
  JSR checkforend
  BCC $03              ; BCC lnloop4
  JMP lnloop
lnloop4
; Read mnemonic and emit opcode
  JSR emitopcode
tokloop
  JSR skipspaces
  JSR checkforend
  BCC $03              ; BCC tokloop1
  JMP lnloop           ; End of line
tokloop1
  CMP# "\""
  BNE $06              ; BNE tokloop2
  JSR emitquoted
  JMP tokloop
tokloop2
  CMP# "$"
  BNE $06              ; BNE tokloop3
  JSR emithex
  JMP tokloop
tokloop3
  CMP# "<"
  BNE $09              ; BNE tokloop4
  JSR read
  JSR emitlabellsb
  JMP tokloop
tokloop4
  CMP# ">"
  BNE $09              ; BNE tokloop5
  JSR read
  JSR emitlabelmsb
  JMP tokloop
tokloop5
  CMP# "~"
  BNE $09              ; BNE tokloop6
  JSR read
  JSR emitlabelrel
  JMP tokloop
tokloop6
  ; label
  JSR emitlabel
  JMP tokloop

; Entry point
start
  LDA# $00
  STAZ <PCL
  STAZ <PCH
  STA LBTAB
  STAZ <PASS
  JSR assemble
  LDA# $00
  STAZ <PCL
  STAZ <PCH
  LDA# $FF
  STAZ <PASS
  JSR assemble
  BRK $00              ; Success


  DATA start ; Emulation environment jumps here
