; Screen calls on the Michael ROM's services: writes, positioning, clear
; to end of row, insert and delete, wrapping past the last column but
; clipping on the bottom row, and '~' and '\'.
  .include rom_vectors.inc

  .org $0200
  ldx #$ff
  txs
  jsr argc                ; starts the services

  goto 1, 1
  print hello             ; "Hello, world"
  goto 1, 6
  lda #1
  jsr scr_delete          ; "Hello world"
  goto 1, 6
  lda #2
  jsr scr_insert
  print xy                ; "HelloXY world"
  goto 2, 3
  print alphabet          ; wraps onto row 3 after column 20
  goto 3, 1
  print tilde_backslash   ; over "st"
  goto 4, 1
  print status
  goto 4, 8
  jsr scr_clear_eol       ; "status "
  goto 4, 15
  print alphabet          ; clipped at column 20
  jsr con_flush           ; Show the screen and stop (exit would go back to the loader)
  stp

hello:           .asciiz "Hello, world"
xy:              .asciiz "XY"
alphabet:        .asciiz "abcdefghijklmnopqrstuvwxyz"
tilde_backslash: .asciiz "~\\"
status:          .asciiz "status line"

  .include print_string.inc
