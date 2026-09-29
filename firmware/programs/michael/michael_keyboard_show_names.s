;TODO: If code is not on the full list of codes that are understood then ignore it?
;      12/8/21 This might be related to key codes that don't map over to set 3. Currently
;      they will not translate to ASCII, but if we look at raw key codes they won't be
;      filtered out

  .include base_config_v2.inc

;INTERRUPT_ROUTINE        = $3f00
INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET

CP_M_DEST_P              = $00 ; 2 bytes
CP_M_SRC_P               = $02 ; 2 bytes
CP_M_LEN                 = $04 ; 2 bytes

CREATE_CHARACTER_PARAM   = $06 ; 2 bytes

SIMPLE_BUFFER_WRITE_PTR  = $08 ; 1 byte
SIMPLE_BUFFER_READ_PTR   = $09 ; 1 byte

CONSOLE_CURSOR_POSITION  = $0a ; 1 byte

TEMP_ZP_BYTE_1           = $0b ; 1 byte
TEMP_ZP_BYTE_2           = $0c ; 1 byte
TEMP_ZP_BYTE_3           = $0d ; 1 byte

DISPLAY_STRING_PARAM     = $0e ; 2 bytes
KB_ZERO_PAGE_BASE        = $10

SIMPLE_BUFFER            = $0200 ; 256 bytes
CONSOLE_TEXT             = $0300 ; CONSOLE_LENGTH + 1 bytes

  .org PROGRAM_LOAD_ADDRESS      ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  ; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
  .include delay_routines.inc
  .include initialize_machine_v2.inc
EXTEND_CHARACTER_SET = 1
  .include display_routines.inc
CONSOLE_WIDTH = DISPLAY_WIDTH
CONSOLE_HEIGHT = DISPLAY_HEIGHT
  .include full_screen_console_flexible_line_based.inc
  .include simple_buffer.inc
  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE = simple_buffer_initialize
KB_BUFFER_WRITE      = simple_buffer_write
KB_BUFFER_READ       = simple_buffer_read
  .include keyboard_driver.inc
  .include convert_to_hex.inc
  .include display_string.inc
  .include key_names.inc


program_start:
  ; Initialize stack
  ldx #$ff
  txs

  ; Initialize functions we will use in this program
  jsr reset_and_enable_display_no_cursor
  jsr console_initialize
  jsr keyboard_initialize

  ; Print ready message
  lda #<ready_message
  ldx #>ready_message
  jsr display_string
  jsr console_print_string
  lda #'\n'
  jsr console_print_character

; Decode and write key codes and names to console
.loop
  jsr console_show
.repeat:
  jsr simple_buffer_read
  bcs .repeat                   ; Exit when input buffer is empty
  jsr keyboard_decode_and_translate
  bcs .repeat                   ; Nothing decoded so far so read more
  jsr keyboard_lock_keys_track
  lda KEYBOARD_LATEST_META
  bit #KB_META_BREAK
  bne .repeat                   ; Decoded key up event; ignore these so read more
  lda KEYBOARD_LATEST_CODE
  jsr print_key_name_to_console
  bra .loop

ready_message: .asciiz 'Ready'


console_print_hex:
  phx
  phy

  jsr convert_to_hex
  jsr console_print_character
  txa
  jsr console_print_character

  jsr console_get_cursor_xy
  cpx #0
  beq .done

;  lda #' '
;  jsr console_print_character

.done:
  ply
  plx
  rts


; Requires DISPLAY_STRING_PARAM - 2 bytes for temporary storage of parameters

; On entry A, X contain low and high bytes of string address
; On exit A, X, Y are preserved
console_print_string:
  pha
  phx
  phy

  sta DISPLAY_STRING_PARAM
  stx DISPLAY_STRING_PARAM + 1
  ldy #0
.print_loop:
  lda (DISPLAY_STRING_PARAM),Y
  beq .done_printing
  jsr console_print_character
  iny
  bra .print_loop
.done_printing:

  ply
  plx
  pla
  rts


; On entry A contains the key code
; On exit A, X, Y are preserved
print_key_name_to_console:
  pha
  phx
  phy
  tay
  jsr name_lookup
  bcs .not_found
  jsr console_print_string
  bra .printed
.not_found
  lda #<unrecognized_key_message
  ldx #>unrecognized_key_message
  jsr console_print_string
  tya
  jsr console_print_hex
.printed
  lda #'\n'
  jsr console_print_character
  ply
  plx
  pla
  rts

unrecognized_key_message: .asciiz 'Unknown Code: '


; On entry A contains the key code
; On exit  A, X contains the low and high bytes of the string address
;          Y is preserved
;          Carry is set if no translation found
name_lookup:
.POINTER_L    = TEMP_ZP_BYTE_1
.POINTER_H    = TEMP_ZP_BYTE_2
.TARGET_VALUE = TEMP_ZP_BYTE_3
  phy
  sta .TARGET_VALUE
  stz .POINTER_L
  lda #>key_names
  sta .POINTER_H
  ldy #<key_names
.word_loop:
  lda (.POINTER_L), Y
  cmp .TARGET_VALUE
  beq .found
.skip_loop:
  iny
  bne .skip_loop_high_ready
  inc .POINTER_H
.skip_loop_high_ready:
  lda (.POINTER_L), Y
  bne .skip_loop
; terminating zero found; check for another zero
  iny
  bne .skip_loop_high_ready_2
  inc .POINTER_H
.skip_loop_high_ready_2:
  lda (.POINTER_L), Y
  bne .word_loop
; not found
  sec
  bra .done
.found:
  iny
  bne .found_high_ready
  inc .POINTER_H
.found_high_ready:
  tya
  ldx .POINTER_H
  clc
.done:
  ply
  rts
