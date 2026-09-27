; exit on the Michael ROM's services: back to the loader, which shows its ready screen.
  .include rom_vectors.inc

  .org $0200
  ldx #$ff
  txs
  jsr argc
  print text
  jmp exit

text: .asciiz "Leaving"

  .include print_string.inc
