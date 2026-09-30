;read_b  = $f006
;write_b = $f009

;TEMP     = $00
;TEMP2    = $01
;MNEMONIC = $02

;LF       = $0A

;  .org $2000

;lnloop:
  JSR F006   ; 2000  jsr read_b
  BCC 03     ; 2003  bcc lnloop1
  JMP 209F   ; 2005  jmp done ; at end of input
;lnloop1:
  JSR 20B2   ; 2008  jsr skipspc
  CMP# ";"   ; 200B  cmp #';'
  BNE 03     ; 200D  bne lnloop2
  JMP 2095   ; 200F  jmp ignln ; comment: skip rest of line
;lnloop2:
  CMP# 0A    ; 2012  cmp #LF ; newline
  BNE 03     ; 2014  bne lnloop3
  JMP 2000   ; 2016  jmp lnloop ; blank line
;lnloop3:
; Read and emit mnemonic
  LDX# 00    ; 2019  ldx #0
;rmloop:
  STAZ,X 02  ; 201B  sta MNEMONIC,X
  INX        ; 201D  inx
  JSR F006   ; 201E  jsr read_b
  CMP# " "   ; 2021  cmp #' '
  BEQ 07     ; 2023  beq rmdone ; done
  CMP# 0A    ; 2025  cmp #LF
  BEQ 03     ; 2027  beq rmdone
  JMP 201B   ; 2029  jmp rmloop
;rmdone:
  STAZ 00    ; 202C  sta TEMP
  LDA# 00    ; 202E  lda #0
  STAZ,X 02  ; 2030  sta MNEMONIC,X
  JSR 20CB   ; 2032  jsr emitoc
  LDAZ 00    ; 2035  lda TEMP

;tokloop:
  JSR 20B2   ; 2037  jsr skipspc
  CMP# ";"   ; 203A  cmp #';'
  BNE 03     ; 203C  bne tokloop1
  JMP 2095   ; 203E  jmp ignln ; handle comment
;tokloop1:
  CMP# 0A    ; 2041  cmp #LF
  BNE 03     ; 2043  bne tokloop2
  JMP 2000   ; 2045  jmp lnloop ; end of line
;tokloop2:
  CMP# "\""  ; 2048  cmp #'"'
  BNE 03     ; 204A  bne tokloop3
  JMP 2078   ; 204C  jmp readqu
;tokloop3:
; Read hex
  JSR 20A0   ; 204F  jsr readhex
  STAZ 01    ; 2052  sta TEMP2
  JSR F006   ; 2054  jsr read_b
  CMP# " "   ; 2057  cmp #' '
  BEQ 11     ; 2059  beq tokloop4
  CMP# 0A    ; 205B  cmp #LF
  BEQ 0D     ; 205D  beq tokloop4
  CMP# ";"   ; 205F  cmp #';'
  BEQ 09     ; 2061  beq tokloop4
  JSR 20A0   ; 2063  jsr readhex
  JSR F009   ; 2066  jsr write_b ; write the low byte
  JSR F006   ; 2069  jsr read_b
;tokloop4:
  STAZ 00    ; 206C  sta TEMP
  LDAZ 01    ; 206E  lda TEMP2
  JSR F009   ; 2070  jsr write_b
  LDAZ 00    ; 2073  lda TEMP
  JMP 2037   ; 2075  jmp tokloop

; read and emit quoted ASCII
;readqu:
  JSR F006   ; 2078  jsr read_b
  CMP# "\""  ; 207B  cmp #'"'
  BNE 03     ; 207D  bne readqu1
  JMP 208F   ; 207F  jmp qudone
;readqu1:
  CMP# "\\"  ; 2082  cmp #'\\'
  BNE 03     ; 2084  bne readqu2
  JSR F006   ; 2086  jsr read_b
;readqu2:
  JSR F009   ; 2089  jsr write_b
  JMP 2078   ; 208C  jmp readqu
;qudone:
  JSR F006   ; 208F  jsr read_b
  JMP 2037   ; 2092  jmp tokloop


;ignln:
  JSR F006   ; 2095  jsr read_b
  CMP# 0A    ; 2098  cmp #LF ; newline
  BNE F9     ; 209A  bne ignln
  JMP 2000   ; 209C  jmp lnloop

;done:
  BRK        ; 209F  brk


;readhex:
  JSR 20BD   ; 20A0  jsr convhex
  ASLA       ; 20A3  asl
  ASLA       ; 20A4  asl
  ASLA       ; 20A5  asl
  ASLA       ; 20A6  asl
  STAZ 00    ; 20A7  sta TEMP
  JSR F006   ; 20A9  jsr read_b
  JSR 20BD   ; 20AC  jsr convhex
  ORAZ 00    ; 20AF  ora TEMP
  RTS        ; 20B1  rts


;skipspc:
  CMP# " "   ; 20B2  cmp #' '
  BNE 06     ; 20B4  bne skipspc2
  JSR F006   ; 20B6  jsr read_b
  JMP 20B2   ; 20B9  jmp skipspc
;skipspc2:
  RTS        ; 20BC  rts


;convhex:
  CMP# "A"   ; 20BD  cmp #'A'
  BCC 06     ; 20BF  bcc convhex1 ; < 'A'
  SBC# "A"   ; 20C1  sbc #'A'
  CLC        ; 20C3  clc
  ADC# 0A    ; 20C4  adc #10
  RTS        ; 20C6  rts
;convhex1:
  SEC        ; 20C7  sec
  SBC# "0"   ; 20C8  sbc #'0
  RTS        ; 20CA  rts


; Emit the opcode
;emitoc:
  LDY# 00    ; 20CB  ldy #0 ; pointer into mnemomics table
;emitoc1: ; outer loop
  LDX# 00    ; 20CD  ldx #0 ; pointer into mnenomic
  LDA,Y 20FA ; 20CF  lda MNTAB,Y
  BEQ 25     ; 20D2  beq emitoc6 ; not found
;invariant: pointed at first char
; first char of mnenomic in table loaded
;emitoc2: ; inner loop
  CMPZ,X 02  ; 20D4  cmp MNEMONIC,X
  BNE 0C     ; 20D6  bne emitoc3 ; no match
  CMP# 00    ; 20D8  cmp #0
  BEQ 16     ; 20DA  beq emitoc5 ; match
  INX        ; 20DC  inx
  INY        ; 20DD  iny
  LDA,Y 20FA ; 20DE  lda MNTAB,Y
  JMP 20D4   ; 20E1  jmp emitoc2 ; inner loop
;emitoc3: ; no match
  LDA,Y 20FA ; 20E4  lda MNTAB,Y
  BEQ 04     ; 20E7  beq emitoc4 ; done skipping
  INY        ; 20E9  iny
  JMP 20E4   ; 20EA  jmp emitoc3
;emitoc4: ; done skipping
  INY        ; 20ED  iny ; move past 0 terminator
  INY        ; 20EE  iny ; move past opcode
  JMP 20CD   ; 20EF  jmp emitoc1 ; outer loop
;emitoc5: ; match
  INY        ; 20F2  iny ; move past 0 terminator
  LDA,Y 20FA ; 20F3  lda MNTAB,Y
  JSR F009   ; 20F6  jsr write_b
;emitoc6: ; not found
  RTS        ; 20F9  rts


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
