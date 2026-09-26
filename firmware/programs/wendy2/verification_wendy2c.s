; Memory-map verification for wendy2c against the PLD.
;
; Each test shows its number, then one mark per check: a tick if it passed,
; a cross if it failed. Marks go two to a character cell, top half first
; then bottom half, and wrap from line 1 onto line 2. Line 2 ends in " OK"
; if every check passed, or " F!" if any failed. With everything passing:
;
;   |1:::::::.2:::::3|    : is a cell with a tick over a tick
;   |:.4:5::6:::7: OK|    . is a cell with a tick over blank
;
; Every mark comes from a `jsr report_result` tagged "RESULT t.n": test t,
; mark n counting from 1 in reading order. So to find a cross in the bottom
; half of the third cell after the "2", search for "RESULT 2.6".
;
; A check reports and carries on, so a failure doesn't hide later results.

  .include base_config_wendy2c.inc

TEMP                   = $02
TEST_VALUE             = $03
TEST_UPPER_VALUE       = $efff
TEST_FIXED_UPPER_VALUE = $f800

; Result mark glyphs are CGRAM codes FIRST_MARK_GLYPH + top + 2 * bottom,
; where top is 0 for a tick or 1 for a cross and bottom is 0 for blank,
; 1 for a tick or 2 for a cross
FIRST_MARK_GLYPH = 1
MARK_GLYPHS      = 6

  .org $4000
  jmp program_entry

  ; Place code for delay_routines at start of page to ensure no page boundary crossings
  ; during timing loops
  .include delay_routines.inc

  .include display_routines_4bit.inc

switch_to_space_return: .word 0
switch_to_space_space: .byte 0
tests_failed: .byte 0
cell: .byte 0     ; Next character cell to draw in, counting across both lines
top_mark: .byte 0 ; Glyph drawn in `cell` still waiting for its bottom half, or 0 if none

program_entry:
  jsr clear_display
  jsr create_mark_glyphs

  stz tests_failed
  stz cell
  stz top_mark

  jsr test_lower_banks           ; 1
  jsr test_upper_banks           ; 2
  jsr test_fixed_upper_ram       ; 3
  jsr test_lower_bank_with_upper ; 4
  jsr test_access_eeprom         ; 5
  jsr test_all                   ; 6
  jsr test_upper_lower_bank_2    ; 7

  ldx #0
  lda tests_failed
  beq .show_status
  ldx #status_failed - status_passed
.show_status:
  lda status_passed,x
  beq .done
  jsr show_character
  inx
  bra .show_status

.done:
  stp

status_passed: .asciiz " OK"
status_failed: .asciiz " F!"


test_lower_banks:
  lda #'1'
  jsr show_character

  ldx #1
.set_value_in_bank:
  txa
  jsr switch_to_space
  stx TEST_VALUE
  inx
  cpx #16
  bne .set_value_in_bank

  ldx #1
.check_value_in_bank:
  txa
  jsr switch_to_space
  cpx TEST_VALUE
  jsr report_result              ; RESULT 1.1..1.15: lower bank n (cfg n) for n = 1..15
  inx
  cpx #16
  bne .check_value_in_bank

  lda #1
  jsr switch_to_space
  rts


test_upper_banks:
  lda #'2'
  jsr show_character

  ldx #%10000
  lda #%00001
  jsr switch_to_space
  stx TEST_UPPER_VALUE

  ldx #%10001
.set_value_in_bank:
  txa
  jsr switch_to_space
  stx TEST_UPPER_VALUE
  inx
  cpx #%11000
  bne .set_value_in_bank

  ldx #%10000
  lda #%00001
  jsr switch_to_space
  cpx TEST_UPPER_VALUE
  jsr report_result              ; RESULT 2.1: upper bank 1 via cfg %00001

  ldx #%10001
.check_value_in_bank:
  txa
  jsr switch_to_space
  cpx TEST_UPPER_VALUE
  jsr report_result              ; RESULT 2.2..2.8: upper bank n via cfg %10001..%10111 for n = 2..8
  inx
  cpx #%11000
  bne .check_value_in_bank

  ; The lower bank 2 cfgs see the same upper banks
  ldx #%10000
  lda #%00010
  jsr switch_to_space
  cpx TEST_UPPER_VALUE
  jsr report_result              ; RESULT 2.9: upper bank 1 via cfg %00010

  ldx #%10001
  ldy #%11001
.check_value_in_bank_copy:
  tya
  jsr switch_to_space
  cpx TEST_UPPER_VALUE
  bne .checked_bank_copy
  inx
  iny
  cpx #%11000
  bne .check_value_in_bank_copy
.checked_bank_copy:
  jsr report_result              ; RESULT 2.10: upper banks 2..8 via cfgs %11001..%11111

  lda #1
  jsr switch_to_space
  rts


test_fixed_upper_ram:
  lda #'3'
  jsr show_character

  ldx #%10001
.set_value_in_bank:
  txa
  jsr switch_to_space
  stz TEST_FIXED_UPPER_VALUE
  inx
  cpx #%11000
  bne .set_value_in_bank

  lda #%10000
  jsr switch_to_space
  lda #1
  sta TEST_FIXED_UPPER_VALUE

  ldx #%10000
.check_value_in_bank:
  txa
  jsr switch_to_space
  lda #1
  cmp TEST_FIXED_UPPER_VALUE
  bne .checked_bank
  inx
  cpx #%11000
  bne .check_value_in_bank
.checked_bank:
  jsr report_result              ; RESULT 3.1: cfgs %10000..%10111 share the $f800 RAM

  ldx #%11000
.check_value_in_bank_copy:
  txa
  jsr switch_to_space
  lda #1
  cmp TEST_FIXED_UPPER_VALUE
  bne .checked_bank_copy
  inx
  cpx #%100000
  bne .check_value_in_bank_copy
.checked_bank_copy:
  jsr report_result              ; RESULT 3.2: cfgs %11000..%11111 share it too

  ; The same page is also the $f800 RAM for the non-C4 configs
  ldx #%00001
.check_value_in_lower_config:
  txa
  jsr switch_to_space
  lda #1
  cmp TEST_FIXED_UPPER_VALUE
  bne .checked_lower_config
  inx
  cpx #%10000
  bne .check_value_in_lower_config
.checked_lower_config:
  jsr report_result              ; RESULT 3.3: cfgs %00001..%01111 share it too

  lda #1
  jsr switch_to_space
  rts


test_lower_bank_with_upper:
  lda #'4'
  jsr show_character

  lda #%00001
  jsr switch_to_space
  lda #1
  sta TEST_VALUE

  lda #%00010
  jsr switch_to_space
  lda #2
  sta TEST_VALUE

  ldx #3
.set_value_in_bank:
  txa
  jsr switch_to_space
  stz TEST_VALUE
  inx
  cpx #16
  bne .set_value_in_bank

  ldx #%10000
.check_value_in_bank:
  txa
  jsr switch_to_space
  lda #1
  cmp TEST_VALUE
  bne .checked_bank
  inx
  cpx #%11000
  bne .check_value_in_bank
.checked_bank:
  jsr report_result              ; RESULT 4.1: cfgs %10000..%10111 see lower bank 1

  ldx #%11000
.check_value_in_bank_copy:
  txa
  jsr switch_to_space
  lda #2
  cmp TEST_VALUE
  bne .checked_bank_copy
  inx
  cpx #%100000
  bne .check_value_in_bank_copy
.checked_bank_copy:
  jsr report_result              ; RESULT 4.2: cfgs %11000..%11111 see lower bank 2

  lda #1
  jsr switch_to_space
  rts


test_access_eeprom:
  lda #'5'
  jsr show_character

  stz $a000
  stz $a000 + 3

  ; cfgs $00, $10 and $18 map upper memory to ROM
  lda #%00000
  jsr check_eeprom_at_a000
  jsr report_result              ; RESULT 5.1: cfg %00000 has ROM at $a000

  lda #%10000
  jsr check_eeprom_at_a000
  jsr report_result              ; RESULT 5.2: cfg %10000 has ROM at $a000

  lda #%11000
  jsr check_eeprom_at_a000
  jsr report_result              ; RESULT 5.3: cfg %11000 has ROM at $a000

  ; cfg=$00 also maps $f800 to ROM: changing the RAM at $f800 (via
  ; cfg=$01) must not change what cfg=$00 reads there
  lda #%00000
  jsr switch_to_space
  ldy TEST_FIXED_UPPER_VALUE

  lda #%00001
  jsr switch_to_space
  tya
  eor #$ff
  sta TEST_FIXED_UPPER_VALUE

  lda #%00000
  jsr switch_to_space
  cpy TEST_FIXED_UPPER_VALUE
  jsr report_result              ; RESULT 5.4: cfg %00000 has ROM at $f800

  lda #1
  jsr switch_to_space
  rts


; On entry A contains the space to check. Returns with Z set if the
; ROM's code is visible at $a000 in that space.
check_eeprom_at_a000:
  jsr switch_to_space
  ldx #0
  lda $a000
  cmp #$20 ; JSR
  bne .not_eeprom

  lda $a000 + 3
  cmp #$A9 ; LDA (immediate)
  bne .not_eeprom

  inx

.not_eeprom:
  lda #1
  jsr switch_to_space
  cpx #1
  rts


; Test 7: write/read-back at $a000 and $e000 for cfgs %11001..%11111
; (the "lower bank 2" upper-bank-select group). Mirrors the test_all
; upper-L / upper-H sub-tests but for the C3=1 group. cfg=%11000 is
; excluded: it maps upper memory to ROM, which must not be written.
test_upper_lower_bank_2:
  lda #'7'
  jsr show_character

  ; Fill phase: each cfg in $19..$1F writes the cfg byte to $a000
  ; and (cfg + $20) to $e000.
  ldx #%11001               ; $19
  lda #%11001
.t7_fill:
  jsr switch_to_space
  stx $a000
  txa
  clc
  adc #$20
  sta $e000
  inx
  txa
  cmp #%100000              ; $20 -- one past the last cfg
  bne .t7_fill

  ; Check phase: same loops but read and compare.
  ldx #%11001
  lda #%11001
.t7_check_l:
  jsr switch_to_space
  cpx $a000
  bne .t7_checked_l
  inx
  txa
  cmp #%100000
  bne .t7_check_l
.t7_checked_l:
  jsr report_result         ; RESULT 7.1: cfgs %11001..%11111 at $a000

  ldx #%11001
.t7_check_h:
  txa
  jsr switch_to_space
  clc
  adc #$20
  cmp $e000
  bne .t7_checked_h
  inx
  cpx #%100000
  bne .t7_check_h
.t7_checked_h:
  jsr report_result         ; RESULT 7.2: cfgs %11001..%11111 at $e000

  lda #1
  jsr switch_to_space
  rts


test_all:
  lda #'6'
  jsr show_character

; Set Values

; 1..15      in lower bank 1..15   config 00001..01111 $2000
  ldx #1
  lda #%00001
.fill_lower_bank:
  jsr switch_to_space
  stx $2000
  inx
  inc
  cmp #%10000
  bne .fill_lower_bank

; 16         in lower fixed ram    config 00001        $6000
  ldx #16
  lda #%00001
  jsr switch_to_space
  stx $6000

; 17         in upper bank 1 L     config 00001        $a000
  ldx #17
  lda #%00001
  jsr switch_to_space
  stx $a000

; 18..24     in upper bank 2..8 L     config 10001..10111 $a000
  ldx #18
  lda #%10001
.fill_upper_bank_l:
  jsr switch_to_space
  stx $a000
  inx
  inc
  cmp #%11000
  bne .fill_upper_bank_l

; 25         in upper bank 1 H     config 00001        $e000
  ldx #25
  lda #%00001
  jsr switch_to_space
  stx $e000

; 26..32     in upper bank 2..8 H  config 10001..10111 $e000
  ldx #26
  lda #%10001
.fill_upper_bank_h:
  jsr switch_to_space
  stx $e000
  inx
  inc
  cmp #%11000
  bne .fill_upper_bank_h

; Check Values

; 1..15      in lower bank 1..15   config 00001..01111 $2000
  ldx #1
  lda #%00001
.check_lower_bank:
  jsr switch_to_space
  cpx $2000
  bne .checked_lower_bank
  inx
  inc
  cmp #%10000
  bne .check_lower_bank
.checked_lower_bank:
  jsr report_result         ; RESULT 6.1: lower banks 1..15 at $2000

; 16         in lower fixed ram    config 00001        $6000
  ldx #16
  lda #%00001
  jsr switch_to_space
  cpx $6000
  jsr report_result         ; RESULT 6.2: lower fixed RAM at $6000

; 17         in upper bank 1 L     config 00001        $a000
  ldx #17
  lda #%00001
  jsr switch_to_space
  cpx $a000
  jsr report_result         ; RESULT 6.3: upper bank 1 at $a000

; 18..24     in upper bank 2..8 L  config 10001..10111 $a000
  ldx #18
  lda #%10001
.check_upper_bank_l:
  jsr switch_to_space
  cpx $a000
  bne .checked_upper_bank_l
  inx
  inc
  cmp #%11000
  bne .check_upper_bank_l
.checked_upper_bank_l:
  jsr report_result         ; RESULT 6.4: upper banks 2..8 at $a000

; 25         in upper bank 1 H     config 00001        $e000
  ldx #25
  lda #%00001
  jsr switch_to_space
  cpx $e000
  jsr report_result         ; RESULT 6.5: upper bank 1 at $e000

; 26..32     in upper bank 2..8 H  config 10001..10111 $e000
  ldx #26
  lda #%10001
.check_upper_bank_h:
  jsr switch_to_space
  cpx $e000
  bne .checked_upper_bank_h
  inx
  inc
  cmp #%11000
  bne .check_upper_bank_h
.checked_upper_bank_h:
  jsr report_result         ; RESULT 6.6: upper banks 2..8 at $e000

  lda #1
  jsr switch_to_space
  rts


; Shows a tick if Z is set (the check passed) or a cross if not, in the
; top half of the next cell or the bottom half of a half-filled one
; On exit A, X, Y are preserved
report_result:
  pha
  phx
  beq .passed               ; pha and phx leave the flags alone
  lda #1
  sta tests_failed
  bra .have_result
.passed:
  lda #0
.have_result:               ; A is 0 if passed, 1 if failed
  ldx top_mark
  bne .bottom_half
  clc
  adc #FIRST_MARK_GLYPH     ; mark over blank
  sta top_mark
  jsr draw_in_cell
  bra .done
.bottom_half:
  inc
  asl                       ; 2 * bottom
  adc top_mark              ; carry is clear after the asl
  jsr draw_in_cell
  stz top_mark
  inc cell
.done:
  plx
  pla
  rts


; Shows character A in a cell of its own, after any half-filled one
; On exit X, Y are preserved
show_character:
  pha
  lda top_mark
  beq .draw
  stz top_mark              ; leave the half-filled cell's bottom blank
  inc cell
.draw:
  pla
  jsr draw_in_cell
  inc cell
  rts


; Draws character A in cell `cell`, wrapping from line 1 onto line 2
; On exit X, Y are preserved
draw_in_cell:
  pha
  lda cell
  cmp #DISPLAY_WIDTH
  bcc .on_first_line
  adc #DISPLAY_SECOND_LINE - DISPLAY_WIDTH - 1 ; carry is set
.on_first_line:
  jsr move_cursor
  pla
  jmp display_character     ; tail call


; Writes the MARK_GLYPHS result mark glyphs to CGRAM, each a symbol over
; a symbol from mark_symbol_rows
create_mark_glyphs:
  lda #(CMD_SET_CGRAM_ADDRESS | (FIRST_MARK_GLYPH * 8))
  jsr display_command
  ldy #0
.glyph:
  tya
  and #1
  inc                       ; top: 1 tick, 2 cross
  jsr write_mark_symbol_rows
  tya
  lsr                       ; bottom: 0 blank, 1 tick, 2 cross
  jsr write_mark_symbol_rows
  iny
  cpy #MARK_GLYPHS
  bne .glyph
  rts


; On entry A = symbol: 0 blank, 1 tick or 2 cross. Writes its 4 CGRAM rows
; On exit Y is preserved
write_mark_symbol_rows:
  asl
  asl
  tax
.row:
  lda mark_symbol_rows,x
  jsr display_character
  inx
  txa
  and #3
  bne .row
  rts


; Each symbol is 3 pixel rows then a blank separator row; a glyph stacks two
mark_symbol_rows:
  ; blank
  .byte %00000
  .byte %00000
  .byte %00000
  .byte %00000
  ; tick
  .byte %00001
  .byte %01010
  .byte %00100
  .byte %00000
  ; cross
  .byte %01010
  .byte %00100
  .byte %01010
  .byte %00000


; On entry A contains the space to switch to
; on exit A, X, Y are preserved
switch_to_space:
  sta switch_to_space_space
  pla
  sta switch_to_space_return
  pla
  sta switch_to_space_return + 1

  lda switch_to_space_space

  and #BANK_MASK
  sta TEMP
  lda BANK_PORT
  and #~BANK_MASK
  ora TEMP
  sta BANK_PORT

  lda switch_to_space_return + 1
  pha
  lda switch_to_space_return
  pha
  lda switch_to_space_space
  rts
