; Maps the RAM below the VIA ($0000-$5FFF), 1K block by block, to find out how much there is.
; Ben Eater's board has 16K: its RAM chip's A14 is grounded and address A14 drives the chip's OE,
; so writes to $4000-$7FFF also land in $0000-$3FFF but reads there find nothing.
;
; Each block is probed at one byte, its "cell" (offset CELL_OFFSET), and shown as a character:
;   R  RAM: reads back what was written, and writing it changes no lower block
;   m  mirror: reads back, but writing it changes a lower block (the same RAM seen twice)
;   w  writes land in a lower block, but reads don't come back (Ben Eater's $4000-$5FFF)
;   -  nothing: reads don't come back and no lower block changes
; The last line gives the RAM that is contiguous from $0000.
; The probe saves every cell first and restores them afterwards, lowest last, so it leaves RAM as
; it found it. The VIA ($6000-$7FFF) and the ROM ($8000) aren't probed.

  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes
TO_DECIMAL_PARAM     = $02 ; 10 bytes
PROBE_P              = $0c ; 2 bytes
BLOCK                = $0e ; 1 byte
LOWER_CHANGED        = $0f ; 1 byte
SAVED                = $10 ; BLOCKS bytes
CLASS                = $28 ; BLOCKS bytes

BLOCKS               = 24  ; 1K blocks from $0000 up to the VIA
BLOCKS_PER_LINE      = 12
CELL_OFFSET          = $ff ; Cells are $00FF, $04FF, $08FF, ...: clear of the variables above,
                           ; the stack and (checked below) this program

  .org PROGRAM_LOAD_ADDRESS
  jmp initialize_machine

  .include initialize_machine_v2.inc
  .include display_routines_8bit.inc
  .include display_string.inc
  .include display_hex.inc
  .include display_decimal.inc

program_start:
  ldx #$ff ; Initialize stack
  txs
  ; Interrupts stay disabled: the loader starts programs with sei

  jsr probe_ram

  jsr clear_display
  lda #DISPLAY_FIRST_LINE
  jsr move_cursor
  lda #<title
  ldx #>title
  jsr display_string

  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  ldx #0
  jsr display_blocks

  lda #DISPLAY_THIRD_LINE
  jsr move_cursor
  ldx #BLOCKS_PER_LINE
  jsr display_blocks

  lda #DISPLAY_FOURTH_LINE
  jsr move_cursor
  jsr display_contiguous_ram

forever:
  bra forever


; Fills CLASS with each block's character, leaving RAM as it was found
; On exit A, X, Y are not preserved
probe_ram:
  lda #CELL_OFFSET
  sta PROBE_P
  ldx #BLOCKS - 1
.save:
  txa
  jsr point_at_cell
  lda (PROBE_P)
  sta SAVED,X
  dex
  bpl .save

  stz BLOCK
.classify:
  jsr check_lower_ram     ; Marks each lower RAM block's cell with its block number
  lda BLOCK
  jsr point_at_cell
  ldy #'-'
  lda #$55
  jsr write_and_compare
  bne .compared
  lda #$aa
  jsr write_and_compare
  bne .compared
  ldy #'R'
.compared:
  jsr check_lower_ram
  beq .store
  cpy #'R'
  beq .mirror
  ldy #'w'
  bra .store
.mirror:
  ldy #'m'
.store:
  ldx BLOCK
  sty CLASS,X
  inc BLOCK
  lda BLOCK
  cmp #BLOCKS
  bne .classify

  ; Highest first, so a block whose writes land in a lower one is put right by the lower one
  ldx #BLOCKS - 1
.restore:
  txa
  jsr point_at_cell
  lda SAVED,X
  sta (PROBE_P)
  dex
  bpl .restore
  rts


; On entry A = block
; On exit  PROBE_P points at the block's cell
;          A is not preserved; X, Y are preserved
point_at_cell:
  asl
  asl
  sta PROBE_P + 1
  rts


; On entry A = value to write to the cell PROBE_P points at
; On exit  Z set if the cell reads back the value
;          A, X, Y are preserved
write_and_compare:
  sta (PROBE_P)
  cmp (PROBE_P)
  rts


; Checks that each RAM block below BLOCK still holds its block number in its cell, then writes
; the number there again
; On exit Z clear if any of those cells had changed
;         A, X are not preserved; Y is preserved
check_lower_ram:
  stz LOWER_CHANGED
  ldx #0
.check:
  cpx BLOCK
  beq .checked
  lda CLASS,X
  cmp #'R'
  bne .next
  txa
  jsr point_at_cell
  txa
  cmp (PROBE_P)
  sta (PROBE_P)
  beq .next
  lda #1
  sta LOWER_CHANGED
.next:
  inx
  bra .check
.checked:
  lda LOWER_CHANGED
  rts


; On entry X = first block to display
; On exit  "<address> " and BLOCKS_PER_LINE characters from CLASS are displayed
;          A, X, Y are not preserved
display_blocks:
  txa
  asl
  asl
  jsr display_hex
  lda #0
  jsr display_hex
  lda #' '
  jsr display_character
  ldy #BLOCKS_PER_LINE
.block:
  lda CLASS,X
  jsr display_character
  inx
  dey
  bne .block
  rts


; On exit "<size>K RAM $0000-$<top>" is displayed for the RAM blocks contiguous from $0000
;         A, X, Y are not preserved
display_contiguous_ram:
  ldx #0
.count:
  lda CLASS,X
  cmp #'R'
  bne .counted
  inx
  cpx #BLOCKS
  bne .count
.counted:
  phx
  txa
  ldx #0
  jsr display_decimal
  lda #<ram_from_0000
  ldx #>ram_from_0000
  jsr display_string
  pla
  asl
  asl
  dec
  jsr display_hex
  lda #$ff
  jmp display_hex ; tail call


title:         .asciiz "RAM map, 1K per char"
ram_from_0000: .asciiz "K RAM $0000-$"

program_end:

  ; The probe would overwrite any of this program that sits on a cell
  .if (program_end - 1 - CELL_OFFSET) / $400 != (PROGRAM_LOAD_ADDRESS - 1 - CELL_OFFSET) / $400
  .fail "michael_ram_map.s overlaps a probe cell"
  .endif
