  .include base_config_v2.inc

;TODO ran into a bug that I can't recreate: scrolled past bottom; entered several
;lines of text; backspaced and it didn't stop at the cursor start position

INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET


; Zero page allocations
GCF_ZERO_PAGE_BASE       = $00

CREATE_CHARACTER_PARAM   = GCF_ZERO_PAGE_STOP ; 2 bytes


; Other memory allocations
SIMPLE_BUFFER            = $0200 ; 256 bytes
GC_LINE_BUFFER           = $0300 ; GD_CHAR_ROWS * GD_CHAR_COLS = 400 bytes including terminating 0


  .org PROGRAM_LOAD_ADDRESS      ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  ; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
  .include delay_routines.inc
  .include initialize_machine_v2.inc
callback_key_f1           = handle_f1
gc_callback_char_received = sk_show_char_info
  .include graphics_console_full.inc
EXTEND_CHARACTER_SET = 1
  .include display_routines.inc
  .include display_string.inc
  .include display_hex.inc
  .include show_keys_on_screen.inc


CT_COMMANDS:
  .asciiz "hello"
                      .word command_hello
  .asciiz "Angel"
                      .word command_angel
  .asciiz "angel"
                      .word command_angel
  .asciiz "echo"
                      .word command_echo
  .asciiz "getchar"
                      .word command_getchar
  .asciiz "clear"
                      .word command_clear
  .asciiz "exit"
                      .word 0
  .byte 0

 
program_start:
  ; Initialize stack
  ldx #$ff
  txs

  jsr gcf_init
  jsr reset_and_enable_display_no_cursor
  jsr sk_init

  jsr cr_repl

  lda #<.exit_message
  ldx #>.exit_message
  jsr gc_putstring

  stp
.exit_message: .asciiz "Exited.\n"


command_hello:
  lda #<.message_string
  ldx #>.message_string
  jsr gc_putstring
  rts

.message_string: .asciiz "Hello, world!\n"


command_angel:
  lda #<.message_string
  ldx #>.message_string
  jsr gc_putstring
  rts

.message_string: .asciiz "Phil :==D Angel :)\n"


command_echo:
  lda #<.command_string
  ldx #>.command_string
  jsr gc_putstring

  jsr gc_getline

  lda #<.message_string
  ldx #>.message_string
  jsr gc_putstring

  jsr gc_show_line_buffer

  rts

.command_string: .asciiz "Enter text: "
.message_string: .asciiz "You entered: "


command_getchar:
  lda #<.command_string
  ldx #>.command_string
  jsr gc_putstring

.loop:
  jsr gc_getchar
  cmp #ASCII_LF
  beq .done
; show in hex
  jsr convert_to_hex
  jsr gc_putchar
  txa
  jsr gc_putchar
  bra .loop
.done:
  rts

.command_string: .asciiz "Enter text: "


command_clear:
  jsr gc_clear
  rts


handle_f1:
  pha
  phx
  phy

  jsr gd_select

  ldy #0
.loop:
  lda .f1_text, Y
  beq .done
  jsr gc_handle_char_from_keyboard
  iny
  bra .loop
.done:
  jsr gd_unselect

  ply
  plx
  pla
  rts
.f1_text: .asciiz "The quick brown fox jumps over the lazy dog. "
