MNEMONIC = $0A00
MNTAB    = $0B00
INPUT    = $0C00
OUTPUT   = $0E00

MNTAB_P  = $00
MN_P     = $02
TEMP     = $04
TEMP2    = $05

INPUT_P  = $80
OUTPUT_P = $82

LF       = $0D

.org $0800

start:
  jsr init_io

; initialize high bytes of pointers
  lda #>MNTAB
  sta MNTAB_P+1
  lda #>MNEMONIC
  sta MN_P+1
; Y register stays at 0 for indexing
  ldy #0

lnloop:
  jsr read_b
  bcc lnloop1
  jmp done ; at end of input
lnloop1:
  jsr skipspc
  cmp #';
  bne lnloop2
  jmp ignln ; comment: skip rest of line
lnloop2:
  cmp #LF ; newline
  bne lnloop3
  jmp lnloop ; blank line
lnloop3:
; Read and emit mnemonic
  sta MNEMONIC
  lda #<MNEMONIC+1
  sta MN_P
rmloop:
  jsr read_b
  cmp #' 
  bne rmloop1
  jmp rmdone
rmloop1:
  cmp #LF
  bne rmloop2
  jmp rmdone
rmloop2:
  sta (MN_P),Y
  inc MN_P
  jmp rmloop
rmdone:
  sta TEMP
  lda #0
  sta (MN_P),Y
  jsr emitoc
  lda TEMP

loop:
  jsr skipspc
  cmp #';
  bne loop1
  jmp ignln ; comment
loop1:
  cmp #LF
  bne loop2
  jmp lnloop ; end of line
loop2:
  cmp #'"
  bne loop3
  jmp readqu
loop3:
; Read hex
  jsr readhex
  sta TEMP2
  jsr read_b
  cmp #' 
  beq loop4
  cmp #LF
  beq loop4
  cmp #';
  beq loop4
  jsr readhex
  jsr write_b ; write the low byte
  jsr read_b
loop4:
  sta TEMP
  lda TEMP2
  jsr write_b
  lda TEMP
  jmp loop

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
  jmp loop


ignln:
  jsr read_b
  cmp #LF ; newline
  bne ignln
  jmp lnloop


; jsr emitoc
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
  sbc #'A-10
  rts
convhex1:
  sec
  sbc #'0
  rts


; Emit the opcode
emitoc:
  lda #<MNTAB
  sta MNTAB_P
emitoc1: ; outer loop
  lda #<MNEMONIC
  sta MN_P
  lda (MNTAB_P),Y
  beq emitoc6 ; not found
;invariant: pointed at first char
; first char of mnenomic in table loaded
emitoc2: ; inner loop
  cmp (MN_P),Y
  bne emitoc3 ; no match
  cmp #0
  beq emitoc5 ; match
  inc MN_P
  inc MNTAB_P
  lda (MNTAB_P),Y
  jmp emitoc2 ; inner loop
emitoc3: ; no match
  lda (MNTAB_P),Y
  beq emitoc4 ; done skipping
  inc MNTAB_P
  jmp emitoc3
emitoc4: ; done skipping
  inc MNTAB_P ; move past 0 terminator
  inc MNTAB_P ; move past opcode
  jmp emitoc1 ; outer loop
emitoc5: ; match
  inc MNTAB_P ; move past 0 terminator
  lda (MNTAB_P),Y
  jsr write_b
emitoc6: ; not found
  rts


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
  lda INPUT_P
  cmp #<INPUT_END
  bne read_b2
  lda INPUT_P+1
  cmp #>INPUT_END
  beq read_b4
read_b2:
  lda (INPUT_P),Y
  inc INPUT_P
  bne read_b3
  inc INPUT_P+1
read_b3:
  clc
  rts
read_b4:
  sec
  rts


write_b:
  sta (OUTPUT_P),Y
  inc OUTPUT_P
  bne write_b1
  inc OUTPUT_P+1
write_b1:
  rts


.org MNEMONIC


; Instruction table
.org MNTAB
.ASCII "LDA"
.BYTE 0, $AD

.ASCII "LDA#"
.BYTE 0, $A9

.ASCII "LDXZ"
.BYTE 0, $A6

.BYTE 0


; Input data
.org INPUT

.ASCII "LDA 1234"
.BYTE LF

INPUT_END:
