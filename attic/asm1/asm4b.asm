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
  DATA "DATA"    $00 $01 $00
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


ignln
  JSR read
  CMP# $0A             ; CMP# LF ; newline
  BNE $F9              ; BNE ignln
  RTS


skipspc
  CMP# " "
  BNE $06              ; BNE skipspc2
  JSR read
  JMP skipspc
skipspc2
  RTS


readtoken
  LDX# $00
readtokenloop
  STAZ,X $06           ; STAZ,X TOKEN
  INX
  JSR read
  CMP# " "
  BEQ $07              ; BEQ readtokendone ; done
  CMP# $0A             ; CMP# LF
  BEQ $03              ; BEQ readtokendone
  JMP readtokenloop
readtokendone
  STAZ $00             ; STAZ TEMP
  LDA# $00
  STAZ,X $06           ; STAZ,X TOKEN
  RTS


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


findintab
findintab1 ; outer loop
  LDA(),Y $02          ; LDA(),Y TAB
  BNE $02              ; BNE findintab2
  ; not found
  SEC
  RTS
;invariant: pointed at first char
; first char of mnenomic in table loaded
findintab2 ; inner loop
  CMP,Y $0006          ; CMP,Y TOKEN
  BNE $0F              ; BNE findintab4 ; no match
  CMP# $00
  BNE $05              ; BNE findintab3
  ; match
  JSR advanceintab
  CLC
  RTS
findintab3
  INY
  LDA(),Y $02          ; LDA(),Y TAB
  JMP findintab2       ; inner loop
findintab4 ; no match
  LDA(),Y $02          ; LDA(),Y TAB
  BEQ $04              ; BEQ findintab5 ; done skipping
  INY
  JMP findintab4
findintab5 ; done skipping
  INY                  ; move past 2 data bytes
  INY
  JSR advanceintab
  JMP findintab1       ; outer loop


capturelabel
  LDA# $00             ; LDA# <LBTAB
  STAZ $02             ; STAZ TAB
  LDA# $30             ; LDA# >LBTAB
  STAZ $03             ; STAZ TAB+1
  JSR findintab
  BCS $12              ; BCS clnotfound
  BRK                  ; duplicate label
  DATA $01 "Duplicate label" $00
clnotfound
clloop
  LDA,Y $0006          ; LDA,Y TOKEN
  STA(),Y $02          ; STA(),Y TAB
  BEQ $04              ; BEQ cldone
  INY
  JMP clloop
cldone
  INY
  LDAZ $04             ; LDAZ PC
  STA(),Y $02          ; STA(),Y TAB
  INY
  LDAZ $05             ; LDAZ PC+1
  STA(),Y $02          ; STA(),Y TAB
  INY
  LDA# $00
  STA(),Y $02          ; STA(),Y TAB
  LDY# $00             ; restore
  RTS


readlabel
  JSR readtoken
  JSR capturelabel
  LDAZ $00             ; LDAZ TEMP
  CMP# $0A             ; CMP# LF
  BEQ $03              ; BEQ readlabel1
  JSR ignln
readlabel1
  RTS


; Emit the opcode
emitoc
  LDA# $00             ; LDA# <MNTAB
  STAZ $02             ; STAZ TAB
  LDA# $20             ; LDA# >MNTAB
  STAZ $03             ; STAZ TAB+1
  JSR findintab
  BCC $13              ; BCC emitoc1
  BRK                  ; Opcode not found
  DATA $02 "Opcode not found" $00
emitoc1
  LDA(),Y $02          ; LDA(),Y TAB
  BEQ $01              ; BEQ emitoc2
  RTS
emitoc2
  INY
  LDA(),Y $02          ; LDA(),Y TAB
  DEY
  JSR emit
  RTS


; read and emit quoted ASCII
emitqu
  JSR read
  CMP# "\""
  BNE $04              ; BNE emitqu1
  JSR read
  RTS
emitqu1
  CMP# "\\"
  BNE $09              ; BNE emitqu2
  JSR read
  CMP# "n"
  BNE $02              ; BNE emitqu2
  LDA# $0A             ; LDA# "\n"
emitqu2
  JSR emit
  JMP emitqu


convhex
  CMP# "A"
  BCC $06              ; BCC convhex1 ; < 'A'
  SBC# "A"
  CLC
  ADC# $0A             ; ADC# 10
  RTS
convhex1
  SEC
  SBC# "0"
  RTS


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


emithex
  JSR read
emithex2
  JSR readhex
  STAZ $01             ; STAZ TEMP2
  JSR read
  CMP# " "
  BEQ $11              ; BEQ emithex3
  CMP# $0A             ; CMP# LF
  BEQ $0D              ; BEQ emithex3
  CMP# ";"
  BEQ $09              ; BEQ emithex3
  JSR readhex
  JSR emit             ; write the low byte
  JSR read
emithex3
  STAZ $00             ; STAZ TEMP
  LDAZ $01             ; LDAZ TEMP2
  JSR emit
  LDAZ $00             ; LDAZ TEMP
  RTS


emitlabel
  JSR readtoken
  LDA# $00             ; LDA# <LBTAB
  STAZ $02             ; STAZ TAB
  LDA# $30             ; LDA# >LBTAB
  STAZ $03             ; STAZ TAB+1
  JSR findintab
  BCC $12              ; BCC emitlabel2
  BRK                  ; Label not found
  DATA $03 "Label not found" $00
emitlabel2
  LDA(),Y $02          ; LDA(),Y TAB
  JSR emit
  INY
  LDA(),Y $02          ; LDA(),Y TAB
  DEY
  JSR emit
  LDAZ $00             ; LDAZ TEMP
  RTS


checkforend
  CMP# ";"
  BNE $05              ; BNE checkforend1
  JSR ignln
  SEC
  RTS
checkforend1
  CMP# $0A             ; CMP# LF
  BNE $02              ; BNE checkforend2
  SEC
  RTS
checkforend2
  CLC
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
  JSR skipspc
  JSR checkforend
  BCC $03              ; BCC lnloop4
  JMP lnloop
lnloop4
; Read and emit mnemonic
  JSR readtoken
  JSR emitoc
  LDAZ $00             ; LDAZ TEMP
tokloop
  JSR skipspc
  JSR checkforend
  BCC $03              ; BCC tokloop1
  JMP lnloop           ; end of line
tokloop1
  CMP# "\""
  BNE $06              ; BNE tokloop2
  JSR emitqu
  JMP tokloop
tokloop2
  CMP# "$"
  BNE $06              ; BNE tokloop3
  JSR emithex
  JMP tokloop
tokloop3
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
