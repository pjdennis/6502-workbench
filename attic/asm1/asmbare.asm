;read_b  = $f006
;write_b = $f009

;TEMP     = $00
;TEMP2    = $01
;MNEMONIC = $02

;  .org $2000

;lnloop:
  JSR F006   ; 2000  read_b
  BCC 03     ; 2003  lnloop1
  JMP 209F   ; 2005  done ; at end of input
;lnloop1:
  JSR 20B2   ; 2008  skipspc
  CMP# ";"   ; 200B
  BNE 03     ; 200D  lnloop2
  JMP 2095   ; 200F  ignln ; comment: skip rest of line
;lnloop2:
  CMP# 0A    ; 2012  line feed
  BNE 03     ; 2014  lnloop3
  JMP 2000   ; 2016  lnloop ; blank line
;lnloop3:
; Read and emit mnemonic
  LDX# 00    ; 2019
;rmloop:
  STAZ,X 02  ; 201B  MNEMONIC
  INX        ; 201D
  JSR F006   ; 201E  read_b
  CMP# " "   ; 2021
  BEQ 07     ; 2023  rmdone ; done
  CMP# 0A    ; 2025  line feed
  BEQ 03     ; 2027  rmdone
  JMP 201B   ; 2029  rmloop
;rmdone:
  STAZ 00    ; 202C  TEMP
  LDA# 00    ; 202E
  STAZ,X 02  ; 2030  MNEMONIC
  JSR 20CB   ; 2032  emitoc
  LDAZ 00    ; 2035  TEMP

;tokloop:
  JSR 20B2   ; 2037  skipspc
  CMP# ";"   ; 203A
  BNE 03     ; 203C  tokloop1
  JMP 2095   ; 203E  ignln ; handle comment
;tokloop1:
  CMP# 0A    ; 2041  line feed
  BNE 03     ; 2043  tokloop2
  JMP 2000   ; 2045  lnloop ; end of line
;tokloop2:
  CMP# "\""  ; 2048
  BNE 03     ; 204A  tokloop3
  JMP 2078   ; 204C  readqu
;tokloop3:
; Read hex
  JSR 20A0   ; 204F  readhex
  STAZ 01    ; 2052  TEMP2
  JSR F006   ; 2054  read_b
  CMP# " "   ; 2057
  BEQ 11     ; 2059  tokloop4
  CMP# 0A    ; 205B  line feed
  BEQ 0D     ; 205D  tokloop4
  CMP# ";"   ; 205F
  BEQ 09     ; 2061  tokloop4
  JSR 20A0   ; 2063  readhex
  JSR F009   ; 2066  write_b ; write the low byte
  JSR F006   ; 2069  read_b
;tokloop4:
  STAZ 00    ; 206C  TEMP
  LDAZ 01    ; 206E  TEMP2
  JSR F009   ; 2070  write_b
  LDAZ 00    ; 2073  TEMP
  JMP 2037   ; 2075  tokloop

; read and emit quoted ASCII
;readqu:
  JSR F006   ; 2078  read_b
  CMP# "\""  ; 207B
  BNE 03     ; 207D  readqu1
  JMP 208F   ; 207F  qudone
;readqu1:
  CMP# "\\"  ; 2082
  BNE 03     ; 2084  readqu2
  JSR F006   ; 2086  read_b
;readqu2:
  JSR F009   ; 2089  write_b
  JMP 2078   ; 208C  readqu
;qudone:
  JSR F006   ; 208F  read_b
  JMP 2037   ; 2092  tokloop


;ignln:
  JSR F006   ; 2095  read_b
  CMP# 0A    ; 2098  line feed
  BNE F9     ; 209A  ignln
  JMP 2000   ; 209C  lnloop

;done:
  BRK        ; 209F


;readhex:
  JSR 20BD   ; 20A0  convhex
  ASLA       ; 20A3
  ASLA       ; 20A4
  ASLA       ; 20A5
  ASLA       ; 20A6
  STAZ 00    ; 20A7  TEMP
  JSR F006   ; 20A9  read_b
  JSR 20BD   ; 20AC  convhex
  ORAZ 00    ; 20AF  TEMP
  RTS        ; 20B1


;skipspc:
  CMP# " "   ; 20B2
  BNE 06     ; 20B4  skipspc2
  JSR F006   ; 20B6  read_b
  JMP 20B2   ; 20B9  skipspc
;skipspc2:
  RTS        ; 20BC


;convhex:
  CMP# "A"   ; 20BD
  BCC 06     ; 20BF  convhex1 ; < 'A'
  SBC# "A"   ; 20C1
  CLC        ; 20C3
  ADC# 0A    ; 20C4
  RTS        ; 20C6
;convhex1:
  SEC        ; 20C7
  SBC# "0"   ; 20C8
  RTS        ; 20CA


; Emit the opcode
;emitoc:
  LDY# 00    ; 20CB  pointer into mnemomics table
;emitoc1: ; outer loop
  LDX# 00    ; 20CD  pointer into mnenomic
  LDA,Y 20FA ; 20CF  MNTAB
  BEQ 25     ; 20D2  emitoc6 ; not found
;emitoc2: ; inner loop
  CMPZ,X 02  ; 20D4  MNEMONIC
  BNE 0C     ; 20D6  emitoc3 ; no match
  CMP# 00    ; 20D8
  BEQ 16     ; 20DA  emitoc5 ; match
  INX        ; 20DC
  INY        ; 20DD
  LDA,Y 20FA ; 20DE  MNTAB
  JMP 20D4   ; 20E1  emitoc2 ; inner loop
;emitoc3: ; no match
  LDA,Y 20FA ; 20E4  MNTAB
  BEQ 04     ; 20E7  emitoc4 ; done skipping
  INY        ; 20E9
  JMP 20E4   ; 20EA  emitoc3
;emitoc4: ; done skipping
  INY        ; 20ED  move past 0 terminator
  INY        ; 20EE  move past opcode
  JMP 20CD   ; 20EF  emitoc1 ; outer loop
;emitoc5: ; match
  INY        ; 20F2  move past 0 terminator
  LDA,Y 20FA ; 20F3  MNTAB
  JSR F009   ; 20F6  write_b
;emitoc6: ; not found
  RTS        ; 20F9


; Instruction table
;MNTAB:        20FA
BYTE "ADC#"    00 69
BYTE "ASLA"    00 0A
BYTE "BCC"     00 90
BYTE "BEQ"     00 F0
BYTE "BNE"     00 D0
BYTE "BRK"     00 00
BYTE "CLC"     00 18
BYTE "CMPZ,X"  00 D5
BYTE "CMP#"    00 C9
BYTE "INX"     00 E8
BYTE "INY"     00 C8
BYTE "JMP"     00 4C
BYTE "JSR"     00 20
BYTE "LDAZ"    00 A5
BYTE "LDA#"    00 A9
BYTE "LDA,Y"   00 B9
BYTE "LDX#"    00 A2
BYTE "LDY#"    00 A0
BYTE "ORAZ"    00 05
BYTE "RTS"     00 60
BYTE "SBC#"    00 E9
BYTE "SEC"     00 38
BYTE "STAZ"    00 85
BYTE "STAZ,X"  00 95
BYTE 00
