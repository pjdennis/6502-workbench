;read_b   = $f006
;write_b  = $f009

;TEMP     = $00 ; 1 byte
;TEMP2    = $01 ; 1 byte
;TAB      = $02 ; 2 bytes
;PC       = $04 ; 2 bytes
;TOKEN    = $06 ; multiple bytes

;PC_START = $2000
;LBTAB    = $3000
;LF       = $0a

;  .org $2000


; Instruction table
MNTAB
;      Mnemonic          Opcode
  DATA "ADC#"    $00 $00 $69
  DATA "ADCZ"    $00 $00 $65
  DATA "ASLA"    $00 $00 $0A
  DATA "BCC"     $00 $00 $90
  DATA "BCS"     $00 $00 $B0
  DATA "BEQ"     $00 $00 $F0
  DATA "BNE"     $00 $00 $D0
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
  DATA "SEC"     $00 $00 $38
  DATA "STA"     $00 $00 $8D
  DATA "STA(),Y" $00 $00 $91
  DATA "STAZ"    $00 $00 $85
  DATA "STAZ,X"  $00 $00 $95
  DATA "TYA"     $00 $00 $98
  DATA "DATA"    $00 $01 $00 ; Directive
  DATA $00


read
  JMP $F006            ; JMP read_b


emit
  JSR $F009            ; JSR write_b
  INCZ $04             ; INCZ PC
  BNE $02              ; BNE emitdone
  INCZ $05             ; INCZ PC+1
emitdone
  RTS


skiprestofline
  JSR read
  CMP# "\n"
  BNE $F9              ; BNE skiprestofline
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
  BNE $05              ; BNE cfe_notsemicolon
  JSR skiprestofline
  SEC
  RTS
cfe_notsemicolon
  CMP# "\n"
  BNE $02              ; BNE cfe_notnewline
  SEC
  RTS
cfe_notnewline
  CLC
  RTS


; On entry A contains first character of token
;          Y = 0
; Reads token into TOKEN (zero terminated)
; On exit TEMP contains next character after token
;         Y = 0
;         A, X are not preserved
readtoken
  LDX# $00
readtokenloop
  STAZ,X $06           ; STAZ,X TOKEN
  INX
  JSR read
  JSR cmpendoftoken
  BEQ $03              ; BEQ rt_done
  JMP readtokenloop
rt_done
  STAZ $00             ; STAZ TEMP
  LDA# $00
  STAZ,X $06           ; STAZ,X TOKEN
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
  ADCZ $02             ; ADCZ TAB
  STAZ $02             ; STAZ TAB
  TYA                  ; A <- 0
  ADCZ $03             ; ADCZ TAB+1
  STAZ $03             ; STAZ TAB+1
  RTS


; On entry TOKEN contains token to find
;          TAB;TAB+1 points to table
;          Y = 0
; On exit C clear if found; set if not found
;         TAB;TAB+1 points to token value if found
;                   or to end of table if not found
;         Y = 0
;         A is not preserved
findintab              ; outer loop
  LDA(),Y $02          ; LDA(),Y TAB
  BNE $02              ; BNE findintab2
  ; not found
  SEC
  RTS
;invariant: pointed at first char
; first char of mnenomic in table loaded
fit_charloop           ; inner loop
  CMP,Y $0006          ; CMP,Y TOKEN
  BNE $0F              ; BNE fit_skipcurrent ; not a match
  CMP# $00
  BNE $05              ; BNE fit_nextchar ; partial match so far
  ; found a match
  JSR advanceintab
  CLC
  RTS
fit_nextchar           ; move to next char
  INY
  LDA(),Y $02          ; LDA(),Y TAB
  JMP fit_charloop     ; inner loop
fit_skipcurrent        ; skip current symbol in table
  LDA(),Y $02          ; LDA(),Y TAB
  BEQ $04              ; BEQ fit_nextsymbol ; done skipping
  INY
  JMP fit_skipcurrent
fit_nextsymbol         ; move to next symbol in table
  INY                  ; move past 2 data bytes
  INY
  JSR advanceintab
  JMP findintab        ; outer loop


readandfindlabel
  JSR readtoken
  LDA# $00             ; LDA# <LBTAB
  STAZ $02             ; STAZ TAB
  LDA# $30             ; LDA# >LBTAB
  STAZ $03             ; STAZ TAB+1
  JMP findintab        ; Tail call


readandfindexistinglabel
  JSR readandfindlabel
  BCS $01              ; BCC rafel_notfound
  RTS
rafel_notfound
  BRK                  ; Label not found
  DATA $03 "Label not found" $00


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
  STAZ $00             ; STAZ TEMP
  JSR read
  JSR convhex
  ORAZ $00             ; ORAZ TEMP
  RTS


nothex
  BRK
  DATA $04 "Expected hex value" $00


hextotable
  JSR read
  JSR skipspaces
  CMP# "$"
  BEQ $03              ; BEQ htt_hexvalue
  JMP nothex
htt_hexvalue
  INY
  INY
  JSR read
  JSR readhex
  STA(),Y $02
  DEY
  JSR read
  JSR readhex
  STA(),Y $02
  INY
  INY  
  LDA# $00
  STA(),Y $02          ; STA(),Y TAB
  LDY# $00
  JSR read
  STAZ $00             ; STAZ TEMP
  RTS


capturelabel
  JSR readandfindlabel
  BCS $12              ; BCS cl_notfound
  BRK                  ; duplicate label
  DATA $01 "Duplicate label" $00
cl_notfound
cl_loop                ; Copy TOKEN to table
  LDA,Y $0006          ; LDA,Y TOKEN
  STA(),Y $02          ; STA(),Y TAB
  BEQ $04              ; BEQ cl_done
  INY
  JMP cl_loop
cl_done                ; Copy value or PC value to table
  LDAZ $00             ; LDAZ TEMP
  JSR skipspaces
  CMP# "="
  BNE $03              ; BNE cl_copypc
  JMP hextotable
cl_copypc
  STAZ $00             ; STAZ TEMP
  INY
  LDAZ $04             ; LDAZ PC
  STA(),Y $02          ; STA(),Y TAB
  INY
  LDAZ $05             ; LDAZ PC+1
  STA(),Y $02          ; STA(),Y TAB
  INY                  ; Terminate table value
  LDA# $00
  STA(),Y $02          ; STA(),Y TAB
  LDY# $00             ; restore Y register
  RTS


readlabel
  JSR capturelabel
  LDAZ $00             ; LDAZ TEMP
  CMP# "\n"
  BEQ $03              ; BEQ rl_done
  JSR skiprestofline
rl_done
  RTS


; emit the opcode
emitopcode
  LDA# $00             ; LDA# <MNTAB
  STAZ $02             ; STAZ TAB
  LDA# $20             ; LDA# >MNTAB
  STAZ $03             ; STAZ TAB+1
  JSR findintab
  BCC $13              ; BCC eo_found
  BRK                  ; Opcode not found
  DATA $02 "Opcode not found" $00
eo_found
  LDA(),Y $02          ; LDA(),Y TAB
  BEQ $01              ; BEQ eo_opcode
  RTS                  ; Not opcode (DATA command)
eo_opcode
  INY
  LDA(),Y $02          ; LDA(),Y TAB
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


; Read 2 to 4 hex characters and emit 1 or 2 bytes
; When 2 bytes, emit LSB then MSB
; Uses TEMP and TEMP2
; On exit A contains next character after hex
emithex
  JSR read
  JSR readhex
  STAZ $01             ; STAZ TEMP2
  JSR read
  JSR cmpendoftoken
  BEQ $09              ; BEQ eh_last
  JSR readhex
  JSR emit             ; write the low byte
  JSR read
eh_last
  STAZ $00             ; STAZ TEMP
  LDAZ $01             ; LDAZ TEMP2
  JSR emit
  LDAZ $00             ; LDAZ TEMP
  RTS


emitlabel
  JSR readandfindexistinglabel
  LDA(),Y $02          ; LDA(),Y TAB
  JSR emit
  INY
  LDA(),Y $02          ; LDA(),Y TAB
  DEY
  JSR emit
  LDAZ $00             ; LDAZ TEMP
  RTS


emitlabellsb
  JSR readandfindexistinglabel
  LDA(),Y $02          ; LDA(),Y TAB
  JSR emit
  LDAZ $00             ; LDAZ TEMP
  RTS


emitlabelmsb
  JSR readandfindexistinglabel
  INY
  LDA(),Y $02          ; LDA(),Y TAB
  DEY
  JSR emit
  LDAZ $00             ; LDAZ TEMP
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
  JSR readlabel
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
  LDAZ $00             ; LDAZ TEMP
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
  LDA# $00             ; LDA# <PC_START
  STAZ $04             ; STAZ PC
  LDA# $20             ; LDA# >PC_START
  STAZ $05             ; STAZ PC+1
  LDA# $00
  STA $3000            ; STA LBTAB
  LDY# $00             ; Y remains 0 (for indirect addressing)
  JSR assemble
  BRK
  DATA $00 ; Success


  DATA start ; Emulation environment jumps here
