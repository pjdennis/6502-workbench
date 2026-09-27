; Shows how the installed loader ROM uses memory, to check which loader ROM a board has.
; - IRQ:   the IRQ vector, the address the ROM expects a program's interrupt handler at
;          (INTERRUPT_VECTOR_TARGET in base_config_v2.inc)
; - RESET: the reset vector (the loader's ORIGIN)
; - LOAD:  the address the loader runs uploaded programs from (PROGRAM_LOAD_ADDRESS).
;          Found by searching the ROM for the loader's final "sei / jmp UPLOAD_TO"; the
;          address shown before the colon is where that jmp's operand is stored.
; - RAM:   a write/read test of RAM from RAM_TEST_START up to the loader's handler at $3F00

  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes
WORD_P               = $02 ; 2 bytes
RAM_TEST_SEED        = $04 ; 1 byte

RESET_VECTOR         = $fffc
IRQ_VECTOR           = $fffe

ROM_START            = $8000
OP_SEI               = $78
OP_JMP               = $4c

RAM_TEST_START       = $2000 ; Must be page aligned
RAM_TEST_END         = $3f00 ; Loader's interrupt handler starts here; must be page aligned

  .org PROGRAM_LOAD_ADDRESS
  jmp initialize_machine

  .include initialize_machine_v2.inc
  .include display_routines_8bit.inc
  .include display_string.inc
  .include display_hex.inc

program_start:
  ldx #$ff ; Initialize stack
  txs

  jsr clear_display

  lda #DISPLAY_FIRST_LINE
  jsr move_cursor
  lda #<irq_label
  ldx #>irq_label
  jsr display_string
  lda #<IRQ_VECTOR
  ldx #>IRQ_VECTOR
  jsr display_address_and_word

  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<reset_label
  ldx #>reset_label
  jsr display_string
  lda #<RESET_VECTOR
  ldx #>RESET_VECTOR
  jsr display_address_and_word

  lda #DISPLAY_THIRD_LINE
  jsr move_cursor
  lda #<load_label
  ldx #>load_label
  jsr display_string
  jsr find_loader_jump
  bcs load_not_found
  lda WORD_P                     ; Point to the jmp operand, 2 bytes after the sei
  clc
  adc #2
  ldx WORD_P + 1
  bcc load_operand_found
  inx
load_operand_found:
  jsr display_address_and_word
  bra show_ram_test
load_not_found:
  lda #<not_found_message
  ldx #>not_found_message
  jsr display_string

show_ram_test:
  ; Shown last since a RAM fault that aliases lower memory may overwrite this program
  lda #DISPLAY_FOURTH_LINE
  jsr move_cursor
  lda #<ram_label
  ldx #>ram_label
  jsr display_string
  lda #$00
  jsr test_ram_pattern
  bcs ram_bad
  lda #$ff
  jsr test_ram_pattern
  bcs ram_bad
  lda #<ok_message
  ldx #>ok_message
  jsr display_string
  bra forever
ram_bad:
  lda #<bad_message
  ldx #>bad_message
  jsr display_string
  lda WORD_P + 1
  jsr display_hex
  lda WORD_P
  jsr display_hex

forever:
  bra forever


; On entry A, X contain low and high bytes of the address of a word
; On exit  "$<address>: <word>" is displayed in hex
;          A, X, Y are preserved
display_address_and_word:
  pha
  phy
  sta WORD_P
  stx WORD_P + 1
  lda #'$'
  jsr display_character
  lda WORD_P + 1
  jsr display_hex
  lda WORD_P
  jsr display_hex
  lda #':'
  jsr display_character
  lda #' '
  jsr display_character
  ldy #1
  lda (WORD_P),Y
  jsr display_hex
  lda (WORD_P)
  jsr display_hex
  ply
  pla
  rts


; On exit C clear and WORD_P = address of the first "sei / jmp" in the ROM, or
;         C set if there is none
;         A, X, Y are not preserved
find_loader_jump:
  stz WORD_P
  lda #>ROM_START
  sta WORD_P + 1
.check:
  lda (WORD_P)
  cmp #OP_SEI
  bne .next
  ldy #1
  lda (WORD_P),Y
  cmp #OP_JMP
  beq .found
.next:
  inc WORD_P
  bne .check
  inc WORD_P + 1
  bne .check
  sec
  rts
.found:
  clc
  rts


; Fills RAM_TEST_START to RAM_TEST_END with a pattern that is unique within each page and
; differs between neighbouring pages, then verifies it
; On entry A = seed for the pattern
; On exit  C clear if all verified, or C set and WORD_P = first failing address
;          A, X, Y are not preserved
test_ram_pattern:
  sta RAM_TEST_SEED
  jsr ram_test_first
.write:
  jsr ram_test_value
  sta (WORD_P)
  jsr ram_test_next
  bne .write
  jsr ram_test_first
.verify:
  jsr ram_test_value
  cmp (WORD_P)
  bne .fail
  jsr ram_test_next
  bne .verify
  clc
  rts
.fail:
  sec
  rts


; On exit WORD_P = RAM_TEST_START
ram_test_first:
  stz WORD_P
  lda #>RAM_TEST_START
  sta WORD_P + 1
  rts


; On exit WORD_P is incremented
;         Z set when WORD_P reaches RAM_TEST_END
ram_test_next:
  inc WORD_P
  bne .done
  inc WORD_P + 1
  lda WORD_P + 1
  cmp #>RAM_TEST_END
.done:
  rts


; On exit A = test value for the address in WORD_P
ram_test_value:
  lda WORD_P
  eor WORD_P + 1
  eor RAM_TEST_SEED
  rts


irq_label:         .asciiz "IRQ   "
reset_label:       .asciiz "RESET "
load_label:        .asciiz "LOAD  "
ram_label:         .asciiz "RAM 2000-3EFF "
not_found_message: .asciiz "not found"
ok_message:        .asciiz "OK"
bad_message:       .asciiz "X"
