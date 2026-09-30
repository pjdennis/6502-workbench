read_b   = $f006
write_b  = $f009

TEMP     = $00 ; 1 byte
TEMP2    = $01 ; 1 byte
TAB      = $02 ; 2 bytes
PC       = $04 ; 2 bytes
TOKEN    = $06 ; multiple bytes

PC_START = $2000
LBTAB    = $3000
LF       = $0a

  .org $2000


; Instruction table
MNTAB:
  .BYTE "ADC#",    0, 0, $69
  .BYTE "ASLA",    0, 0, $0A
  .BYTE "BCC",     0, 0, $90
  .BYTE "BCS",     0, 0, $B0
  .BYTE "BEQ",     0, 0, $F0
  .BYTE "BNE",     0, 0, $D0
  .BYTE "BRK",     0, 0, $00
  .BYTE "CLC",     0, 0, $18
  .BYTE "CMPZ,X",  0, 0, $D5
  .BYTE "CMP#",    0, 0, $C9
  .BYTE "INCZ",    0, 0, $E6
  .BYTE "INX",     0, 0, $E8
  .BYTE "INY",     0, 0, $C8
  .BYTE "JMP",     0, 0, $4C
  .BYTE "JSR",     0, 0, $20
  .BYTE "LDAZ",    0, 0, $A5
  .BYTE "LDA#",    0, 0, $A9
  .BYTE "LDA(),Y", 0, 0, $B1
  .BYTE "LDA,Y",   0, 0, $B9
  .BYTE "LDX#",    0, 0, $A2
  .BYTE "LDY#",    0, 0, $A0
  .BYTE "ORAZ",    0, 0, $05
  .BYTE "RTS",     0, 0, $60
  .BYTE "SBC#",    0, 0, $E9
  .BYTE "SEC",     0, 0, $38
  .BYTE "STA",     0, 0, $8D
  .BYTE "STA(),Y", 0, 0, $91
  .BYTE "STAZ",    0, 0, $85
  .BYTE "STAZ,X",  0, 0, $95
  .BYTE "DATA",    0, 1, $00
  .BYTE 0

read:
  jmp read_b


emit:
  jsr write_b
  inc PC
  bne emitdone
  inc PC+1
emitdone:
  rts


ignln:
  jsr read
  cmp #LF ; newline
  bne ignln
  rts


skipspc:
  cmp #' '
  bne skipspc2
  jsr read
  jmp skipspc
skipspc2:
  rts


readtoken:
  ldx #0
readtokenloop:
  sta TOKEN,X
  inx
  jsr read
  cmp #' '
  beq readtokendone ; done
  cmp #LF
  beq readtokendone
  jmp readtokenloop
readtokendone:
  sta TEMP
  lda #0
  sta TOKEN,X
  rts


inctab:
  inc TAB
  bne inctabdone
  inc TAB + 1
inctabdone:
  rts


findintab:
findintab1: ; outer loop
  ldx #0 ; pointer into mnenomic
  lda (TAB),Y
  bne findintab2
  ; not found
  sec
  rts
;invariant: pointed at first char
; first char of mnenomic in table loaded
findintab2: ; inner loop
  cmp TOKEN,X
  bne findintab4 ; no match
  cmp #0
  bne findintab3
  ; match
  jsr inctab ; move past 0 terminator
  clc
  rts
findintab3:
  inx
  jsr inctab
  lda (TAB),Y
  jmp findintab2 ; inner loop
findintab4: ; no match
  lda (TAB),Y
  beq findintab5 ; done skipping
  jsr inctab
  jmp findintab4
findintab5: ; done skipping
  jsr inctab ; move past 0 terminator
  jsr inctab ; move past opcode
  jsr inctab ; move past dummy byte
  jmp findintab1 ; outer loop


capturelabel:
  lda #<LBTAB
  sta TAB
  lda #>LBTAB
  sta TAB+1
  jsr findintab
  bcs clnotfound
  brk ; duplicate label
  .BYTE 1, "Duplicate label", 0
clnotfound:
clloop:
  lda TOKEN,Y
  sta (TAB),Y
  beq cldone
  iny
  jmp clloop
cldone:
  iny
  lda PC
  sta (TAB),Y
  iny
  lda PC+1
  sta (TAB),Y
  iny
  lda #0
  sta (TAB),Y
  ldy #0 ; restore
  rts


readlabel:
  jsr readtoken
  jsr capturelabel
  lda TEMP
  cmp #LF
  beq readlabel1
  jsr ignln
readlabel1:
  rts


; Emit the opcode
emitoc:
  lda #<MNTAB
  sta TAB
  lda #>MNTAB
  sta TAB+1
  jsr findintab
  bcc emitoc1
  brk ; Opcode not found
  .BYTE 2, "Opcode not found", 0
emitoc1:
  lda (TAB),Y
  beq emitoc2
  rts
emitoc2:
  jsr inctab
  lda (TAB),Y
  jsr emit
  rts


; read and emit quoted ASCII
emitqu:
  jsr read
  cmp #'"'
  bne emitqu1
  jsr read
  rts
emitqu1:
  cmp #'\\'
  bne emitqu2
  jsr read
emitqu2:
  jsr emit
  jmp emitqu


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


readhex:
  jsr convhex
  asl
  asl
  asl
  asl
  sta TEMP
  jsr read
  jsr convhex
  ora TEMP
  rts


emithex:
  jsr read
emithex2:
  jsr readhex
  sta TEMP2
  jsr read
  cmp #' '
  beq emithex3
  cmp #LF
  beq emithex3
  cmp #';'
  beq emithex3
  jsr readhex
  jsr emit ; write the low byte
  jsr read
emithex3:
  sta TEMP
  lda TEMP2
  jsr emit
  lda TEMP
  rts


emitlabel:
  jsr readtoken
  lda #<LBTAB
  sta TAB
  lda #>LBTAB
  sta TAB+1
  jsr findintab
  bcc emitlabel2
  brk ; Label not found
  .BYTE 3, "Label not found", 0
emitlabel2:
  lda (TAB),Y
  jsr emit
  jsr inctab
  lda (TAB),Y
  jsr emit
  lda TEMP
  rts


checkforend:
  cmp #';'
  bne checkforend1
  jsr ignln
  sec
  rts
checkforend1:
  cmp #LF
  bne checkforend2
  sec
  rts
checkforend2:
  clc
  rts


assemble:
lnloop:
  jsr read
  bcc lnloop1
  rts ; at end of input
lnloop1:
  jsr checkforend
  bcc lnloop2
  jmp lnloop
lnloop2:
  cmp #' '
  beq lnloop3
  jsr readlabel
  jmp lnloop
lnloop3:
  jsr skipspc
  jsr checkforend
  bcc lnloop4
  jmp lnloop
lnloop4:
; Read and emit mnemonic
  jsr readtoken
  jsr emitoc
  lda TEMP
tokloop:
  jsr skipspc
  jsr checkforend
  bcc tokloop1
  jmp lnloop ; end of line
tokloop1:
  cmp #'"'
  bne tokloop2
  jsr emitqu
  jmp tokloop
tokloop2:
  cmp #'$'
  bne tokloop3
  jsr emithex
  jmp tokloop
tokloop3:
  ; label
  jsr emitlabel
  jmp tokloop


start:
  lda #<PC_START
  sta PC
  lda #>PC_START
  sta PC+1
  lda #0
  sta LBTAB
  ldy #0 ; Y remains 0 (for indirect addressing)
  jsr assemble
  brk
  ; .BYTE $42, "Simulated failure", 0
  .BYTE 0 ; Success


  .WORD start ; Emulation environment jumps here
