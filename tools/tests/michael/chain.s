; A program's own interrupt handler ahead of the ROM's: after SVC_START it points the jmp at
; ROM_IRQ_JMP at its handler, which counts interrupts and goes on to SVC_IRQ. Shows the key read
; and 'Y' if the handler ran.
  .include rom_vectors.inc

COUNT = $10

  .org $0200
start:
  ldx #$ff
  txs
  stz COUNT
  jsr SVC_START
  sei
  lda #<handler
  sta ROM_IRQ_JMP + 1
  lda #>handler
  sta ROM_IRQ_JMP + 2
  cli
  jsr con_read
  jsr write_b
  lda #'N'
  ldx COUNT
  beq .show
  lda #'Y'
.show:
  jsr write_b
  jsr con_flush
  stp

handler:
  inc COUNT
  bne .counted
  dec COUNT                       ; Stay non-zero
.counted:
  jmp SVC_IRQ
