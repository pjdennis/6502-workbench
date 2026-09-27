  .include base_config_v2.inc

BEEB_LOAD_ADDRESS        = $0900 ; upload_and_run_michael_beeb.s's UPLOAD_TO

INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET


; Zero page allocations
ZERO_PAGE_BASE           = $00

CP_M_DEST_P              = ZERO_PAGE_BASE + $00 ; 2 bytes
CP_M_SRC_P               = ZERO_PAGE_BASE + $02 ; 2 bytes
CP_M_LEN                 = ZERO_PAGE_BASE + $04 ; 2 bytes

DISPLAY_STRING_PARAM     = ZERO_PAGE_BASE + $06 ; 2 bytes
MULTIPLY_8X8_RESULT_LOW  = ZERO_PAGE_BASE + $08 ; 1 byte
MULTIPLY_8X8_TEMP        = ZERO_PAGE_BASE + $09 ; 1 byte

NEXT_CODE                = ZERO_PAGE_BASE + $0a ; 1 byte
NEXT_CODE_PRESENT        = ZERO_PAGE_BASE + $0b ; 1 byte
NEXT_CHAR                = ZERO_PAGE_BASE + $0c ; 1 byte


GD_ZERO_PAGE_BASE        = ZERO_PAGE_BASE + $0d

KB_ZERO_PAGE_BASE        = GD_ZERO_PAGE_STOP


; Other memory allocations
GC_LINE_BUFFER           = $0300 ; GD_CHAR_ROWS * GD_CHAR_COLS = 400 bytes including terminating 0


  .org BEEB_LOAD_ADDRESS         ; Loader loads programs to this address
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  .include delay_routines.inc    ; Include first since placement on page boundary is necessary

; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
  .include initialize_machine_v2.inc

  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE    = code_buffer_initialize
KB_BUFFER_WRITE         = code_buffer_write
KB_BUFFER_READ          = code_buffer_read
callback_key_esc        = escape
KB_NO_INTERRUPT_HANDLER = 1
  .include keyboard_driver.inc
  .include multiply8x8.inc
  .include graphics_display.inc
  .include graphics_out.inc
  .include write_string_to_screen.inc

 
program_start:
  ; Initialize stack
  ldx #$ff
  txs

  invoke_copy_memory INTERRUPT_ROUTINE,interrupt,interrupt_end

  jsr gd_prepare_vertical
  jsr gc_initialize
  jsr keyboard_initialize

  stz NEXT_CHAR

.start:
  lda #'$'
  jsr gc_putchar

.loop:
  lda NEXT_CHAR
  beq .loop
  stz NEXT_CHAR

  cmp #ASCII_BACKSPACE
  beq .backspace

  cmp #$1b
  beq .escape

  jsr gc_putchar
  bra .loop

.backspace:
  lda GD_COL
  beq .loop ; At start of line - do nothing

  dec GD_COL
  lda #' '
  jsr gc_putchar
  dec GD_COL
  bra .loop

.escape:
  jsr gc_clear
  bra .start


escape:
  pha
  lda #$1b
  sta NEXT_CHAR
  pla
  rts


code_buffer_initialize:
  stz NEXT_CODE_PRESENT
  rts


code_buffer_write:
  sta NEXT_CODE
  inc NEXT_CODE_PRESENT
  clc
  rts


code_buffer_read:
  lda NEXT_CODE_PRESENT
  beq .empty
  lda NEXT_CODE
  stz NEXT_CODE_PRESENT
  clc
  rts
.empty
  sec
  rts


interrupt:
  pha
  jsr handle_keyboard_interrupt
  jsr keyboard_get_char
  bcs .done

  sta NEXT_CHAR

.done:
  pla
  rti
interrupt_end:

