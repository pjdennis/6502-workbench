read_b  = $f006
write_b = $f009

TEMP     = $00
TEMP2    = $01
MNEMONIC = $02

LF       = $0A

  .org $2000

lnloop:
  jsr read_b
  bcc lnloop1
  jmp done ; at end of input
lnloop1:
  jsr skipspc
  cmp #';'
  bne lnloop2
  jmp ignln ; comment: skip rest of line
lnloop2:
  cmp #LF ; newline
  bne lnloop3
  jmp lnloop ; blank line
lnloop3:
; Read and emit mnemonic
  ldx #0
rmloop:
  sta MNEMONIC,X
  inx
  jsr read_b
  cmp #' '
  beq rmdone ; done
  cmp #LF
  beq rmdone
  jmp rmloop
rmdone:
  sta TEMP
  lda #0
  sta MNEMONIC,X
  jsr emitoc
  lda TEMP

tokloop:
  jsr skipspc
  cmp #';'
  bne tokloop1
  jmp ignln ; handle comment
tokloop1:
  cmp #LF
  bne tokloop2
  jmp lnloop ; end of line
tokloop2:
  cmp #'"'
  bne tokloop3
  jmp readqu
tokloop3:
; Read hex
  jsr readhex
  sta TEMP2
  jsr read_b
  cmp #' '
  beq tokloop4
  cmp #LF
  beq tokloop4
  cmp #';'
  beq tokloop4
  jsr readhex
  jsr write_b ; write the low byte
  jsr read_b
tokloop4:
  sta TEMP
  lda TEMP2
  jsr write_b
  lda TEMP
  jmp tokloop

; read and emit quoted ASCII
readqu:
  jsr read_b
  cmp #'"'
  bne readqu1
  jmp qudone
readqu1:
  cmp #'\\'
  bne readqu2
  jsr read_b
readqu2:
  jsr write_b
  jmp readqu
qudone:
  jsr read_b
  jmp tokloop


ignln:
  jsr read_b
  cmp #LF ; newline
  bne ignln
  jmp lnloop

done:
  brk


readhex:
  jsr convhex
  asl
  asl
  asl
  asl
  sta TEMP
  jsr read_b
  jsr convhex
  ora TEMP
  rts


skipspc:
  cmp #' '
  bne skipspc2
  jsr read_b
  jmp skipspc
skipspc2:
  rts


convhex:
  cmp #'A'
  bcc convhex1 ; < 'A'
  sbc #'A'
  clc
  adc #10
  rts
convhex1:
  sec
  sbc #'0'
  rts


; Emit the opcode
emitoc:
  ldy #0 ; pointer into mnemomics table
emitoc1: ; outer loop
  ldx #0 ; pointer into mnenomic
  lda MNTAB,Y
  beq emitoc6 ; not found
;invariant: pointed at first char
; first char of mnenomic in table loaded
emitoc2: ; inner loop
  cmp MNEMONIC,X
  bne emitoc3 ; no match
  cmp #0
  beq emitoc5 ; match
  inx
  iny
  lda MNTAB,Y
  jmp emitoc2 ; inner loop
emitoc3: ; no match
  lda MNTAB,Y
  beq emitoc4 ; done skipping
  iny
  jmp emitoc3
emitoc4: ; done skipping
  iny ; move past 0 terminator
  iny ; move past opcode
  jmp emitoc1 ; outer loop
emitoc5: ; match
  iny ; move past 0 terminator
  lda MNTAB,Y
  jsr write_b
emitoc6: ; not found
  rts


; Instruction table
MNTAB:
  .BYTE "ADC#",   0, $69
  .BYTE "ASLA",   0, $0A
  .BYTE "BCC",    0, $90
  .BYTE "BEQ",    0, $F0
  .BYTE "BNE",    0, $D0
  .BYTE "BRK",    0, $00
  .BYTE "CLC",    0, $18
  .BYTE "CMPZ,X", 0, $D5
  .BYTE "CMP#",   0, $C9
  .BYTE "INX",    0, $E8
  .BYTE "INY",    0, $C8
  .BYTE "JMP",    0, $4C
  .BYTE "JSR",    0, $20
  .BYTE "LDAZ",   0, $A5
  .BYTE "LDA#",   0, $A9
  .BYTE "LDA,Y",  0, $B9
  .BYTE "LDX#",   0, $A2
  .BYTE "LDY#",   0, $A0
  .BYTE "ORAZ",   0, $05
  .BYTE "RTS",    0, $60
  .BYTE "SBC#",   0, $E9
  .BYTE "SEC",    0, $38
  .BYTE "STAZ",   0, $85
  .BYTE "STAZ,X", 0, $95
  .BYTE 0
