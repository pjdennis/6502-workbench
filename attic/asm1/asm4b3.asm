read     = $F006 ; Provided by emulation environment
write_b  = $F009 ; provided by emulation environment

TEMP     = $0000 ; 1 byte
NEXTCHAR = $0001 ; 1 byte
TABL     = $0002 ; 1 byte
TABH     = $0003 ; 1 byte
PCL      = $0004 ; 1 byte
PCH      = $0005 ; 1 byte
HEX1     = $0006 ; 1 byte
HEX2     = $0007 ; 1 byte
TOKEN    = $0008 ; multiple bytes

PC_START = $2000
LBTAB    = $3000

;  .org $2000


; Emulation environment surfaces error codes and messages
err_labelnotfound
  BRK
  DATA $01 "Label not found" $00

err_duplicatelabel
  BRK
  DATA $02 "Duplicate label" $00

err_opcodenotfound
  BRK
  DATA $03 "Opcode not found" $00

err_expectedhex
  BRK
  DATA $04 "Expected hex value" $00


; Instruction table
MNTAB
;      Mnemonic          Opcode
  DATA "ADC#"    $00 $00 $69
  DATA "ADCZ"    $00 $00 $65
  DATA "ASLA"    $00 $00 $0A
  DATA "BCC"     $00 $00 $90
  DATA "BCS"     $00 $00 $B0
  DATA "BEQ"     $00 $00 $F0
  DATA "BITZ"    $00 $00 $24
  DATA "BMI"     $00 $00 $30
  DATA "BNE"     $00 $00 $D0
  DATA "BPL"     $00 $00 $10
  DATA "BRK"     $00 $00 $00
  DATA "CLC"     $00 $00 $18
  DATA "CMPZ,X"  $00 $00 $D5
  DATA "CMP#"    $00 $00 $C9
  DATA "CMP,Y"   $00 $00 $D9
  DATA "DEY"     $00 $00 $88
  DATA "INCZ"    $00 $00 $E6
  DATA "INX"     $00 $00 $E8
  DATA "INY"     $00 $00 $C8
  DATA "JMP"     $00 $00 $4C
  DATA "JSR"     $00 $00 $20
  DATA "LDAZ"    $00 $00 $A5
  DATA "LDA#"    $00 $00 $A9
  DATA "LDA(),Y" $00 $00 $B1
  DATA "LDA,Y"   $00 $00 $B9
  DATA "LDX#"    $00 $00 $A2
  DATA "LDY#"    $00 $00 $A0
  DATA "ORAZ"    $00 $00 $05
  DATA "RTS"     $00 $00 $60
  DATA "SBC#"    $00 $00 $E9
  DATA "SBCZ"    $00 $00 $E5
  DATA "SEC"     $00 $00 $38
  DATA "STA"     $00 $00 $8D
  DATA "STA(),Y" $00 $00 $91
  DATA "STAZ"    $00 $00 $85
  DATA "STAZ,X"  $00 $00 $95
  DATA "TYA"     $00 $00 $98
  DATA "DATA"    $00 $01 $00 ; Directive
  DATA $00


emit
  JSR write_b
  INCZ <PCL
  BNE $02              ; BNE emitdone
  INCZ <PCH
emitdone
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
;          Y = 0
; Reads token into TOKEN (zero terminated)
; On exit NEXTCHAR contains next character after token
;         Y = 0
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
; On exit TAB;TAB+1 += Y
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
;          TAB;TAB+1 points to table
;          Y must equal 0
; On exit C clear if found; set if not found
;         TABL;TABH points to token value if found
;                   or to end of table if not found
;         Y = 0
;         A is not preserved
findintab              ; outer loop
  LDA(),Y <TABL
  BNE $02              ; BNE findintab2
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
fit_nextchar           ; move to next char
  INY
  LDA(),Y <TABL
  JMP fit_charloop     ; inner loop
fit_skipcurrent        ; skip current symbol in table
  LDA(),Y <TABL
  BEQ $04              ; BEQ fit_nextsymbol ; done skipping
  INY
  JMP fit_skipcurrent
fit_nextsymbol         ; move to next symbol in table
  INY                  ; move past 2 data bytes
  INY
  JSR advanceintab
  JMP findintab        ; outer loop


; On entry TOKEN contains a label
;          Y must equal 0
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
  JSR findlabel
  BCS $01              ; BCC rafel_notfound
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
  BCC $05              ; BCS eh_one
  LDAZ <HEX2
  JSR emit
eh_one
  LDAZ <HEX1
  JSR emit
  LDAZ <NEXTCHAR
  RTS


; On exit C set if value read; clear otherwise
readvalue
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
  LDAZ <NEXTCHAR
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
  LDAZ <NEXTCHAR
  JSR readvalue
  STAZ <NEXTCHAR
  BCS $08              ; BNE cl_hextotable
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
  LDY# $00             ; restore Y register
  RTS


; emit the opcode
; On exit NEXTCHAR contains the next character
emitopcode
  LDA# <MNTAB
  STAZ <TABL
  LDA# >MNTAB
  STAZ <TABH
  JSR findintab
  BCC $03              ; BCC eo_found
  JMP err_opcodenotfound
eo_found
  LDA(),Y <TABL
  BEQ $01              ; BEQ eo_opcode
  RTS                  ; Not opcode (DATA command)
eo_opcode
  INY
  LDA(),Y <TABL
  DEY
  JSR emit
  RTS


; read and emit quoted ASCII
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
  DEY
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
  DEY
  JSR emit
  LDAZ <NEXTCHAR       ; Load next character
  RTS


assemble
lnloop
  JSR read
  BCC $01              ; BCC lnloop1
  RTS                  ; at end of input
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
  JSR readtoken
  JSR emitopcode
  LDAZ <NEXTCHAR
tokloop
  JSR skipspaces
  JSR checkforend
  BCC $03              ; BCC tokloop1
  JMP lnloop           ; end of line
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
  ; label
  JSR emitlabel
  JMP tokloop


start
  LDA# <PC_START
  STAZ <PCL
  LDA# >PC_START
  STAZ <PCH
  LDY# $00             ; Y remains 0 (for indirect addressing)
  TYA                  ; A <- 0
  STA LBTAB
  JSR assemble
  BRK
  DATA $00 ; Success


  DATA start ; Emulation environment jumps here
