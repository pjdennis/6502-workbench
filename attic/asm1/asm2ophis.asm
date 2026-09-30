INPUT    = $0C00
OUTPUT   = $0E00

TEMP     = $00
TEMP2    = $01
MNEMONIC = $02

INPUT_P  = $80
OUTPUT_P = $82
IOTEMP   = $84

LF       = $0D

.org $0800

start:
  jsr init_io

lnloop:
  jsr read_b
  bcc lnloop1
  jmp done ; at end of input
lnloop1:
  jsr skipspc
  cmp #";"
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
  cmp #'\ 
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
  cmp #';
  bne tokloop1
  jmp ignln ; handle comment
tokloop1:
  cmp #LF
  bne tokloop2
  jmp lnloop ; end of line
tokloop2:
  cmp #'"
  bne tokloop3
  jmp readqu
tokloop3:
; Read hex
  jsr readhex
  sta TEMP2
  jsr read_b
  cmp #' 
  beq tokloop4
  cmp #LF
  beq tokloop4
  cmp #';
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
  cmp #'"
  bne readqu1
  jmp qudone
readqu1:
  cmp #'\
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
  cmp #' 
  bne skipspc2
  jsr read_b
  jmp skipspc
skipspc2:
  rts


convhex:
  cmp #'A
  bcc convhex1 ; < 'A'
  sbc #'A
  clc
  adc #10
  rts
convhex1:
  sec
  sbc #'0
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
.ASCII "LDA"
.BYTE 0, $AD

.ASCII "LDA#"
.BYTE 0, $A9

.ASCII "LDXZ"
.BYTE 0, $A6

.BYTE 0


; IO and imput data
; (not part of assembler proper)
init_io:
  lda #<INPUT
  sta INPUT_P
  lda #>INPUT
  sta INPUT_P+1

  lda #<OUTPUT
  sta OUTPUT_P
  lda #>OUTPUT
  sta OUTPUT_P+1
  rts


read_b:
  sty IOTEMP
  ldy #0
  lda (INPUT_P),Y
  ldy IOTEMP
  cmp #0
  bne read_b2 ; at end
  sec
  rts
read_b2:
  inc INPUT_P
  bne read_b3
  inc INPUT_P+1
read_b3:
  clc
  rts


write_b:
  sty IOTEMP
  ldy #0
  sta (OUTPUT_P),Y
  ldy IOTEMP
  inc OUTPUT_P
  bne write_b1
  inc OUTPUT_P+1
write_b1:
  rts


; Input data
.org INPUT

.ASCII "LDA 1234"
.BYTE LF
.BYTE 0
