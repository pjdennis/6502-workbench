;TODO: If code is not on the full list of codes that are understood then ignore it?
;      12/8/21 This might be related to key codes that don't map over to set 3. Currently
;      they will not translate to ASCII, but if we look at raw key codes they won't be
;      filtered out

  .include base_config_v2.inc

INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET

CP_M_DEST_P              = $00 ; 2 bytes
CP_M_SRC_P               = $02 ; 2 bytes
CP_M_LEN                 = $04 ; 2 bytes

CREATE_CHARACTER_PARAM   = $06 ; 2 bytes

SIMPLE_BUFFER_WRITE_PTR  = $08 ; 1 byte
SIMPLE_BUFFER_READ_PTR   = $09 ; 1 byte

CONSOLE_CURSOR_POSITION  = $0A ; 1 byte

KB_ZERO_PAGE_BASE        = $0B

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
callback_key_left    = console_cursor_left
callback_key_right   = console_cursor_right
callback_key_esc     = clear_console
  .include keyboard_driver.inc
  .include convert_to_hex.inc


program_start:
  ; Initialize stack
  ldx #$ff
  txs

  ; Initialize functions we will use in this program
  jsr reset_and_enable_display_no_cursor
  jsr console_initialize
  jsr keyboard_initialize

  jsr clear_console

  ; Read and display translated characters from the keyboard
get_char_loop:
  jsr keyboard_get_char
  bcs get_char_loop
get_char_loop_2:
  jsr console_print_character
  jsr keyboard_get_char
  bcc get_char_loop_2
  jsr console_show
  bra get_char_loop


clear_console:
  pha
  jsr console_clear
  ; Show prompt
  lda #">"
  jsr console_print_character
  jsr console_show
  pla
  rts


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

  lda #' '
  jsr console_print_character

.done:
  ply
  plx
  rts
