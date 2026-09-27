; Services for the asm2 editor's define:direct_io, define:michael build:
; its environment vectors (toolchain/asm2/17/environment.asm) on Michael,
; with the 20x4 LCD as the screen and the PS/2 keyboard for input. Loaded
; into RAM with the editor (michael_editor_layout.inc); no file I/O.
;
; The editor clears zero page at start-up and then calls argc before any
; other service, so argc starts the hardware: zero page from $F0 up is the
; services' own from then on.
;
; exit stops the CPU (STP): press reset to get back to the loader.

  .include base_config_v2.inc
  .include michael_editor_layout.inc

; Zero page
KB_ZERO_PAGE_BASE        = $f0 ; 10 bytes
CP_M_DEST_P              = $fa ; 2 bytes (start-up only)
CREATE_CHARACTER_PARAM   = $fa ; 2 bytes (start-up only)
CP_M_SRC_P               = $fc ; 2 bytes (start-up only)

; RAM in the interrupt page, after the 6-byte handler copied there
INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET
KB_RING                  = INTERRUPT_ROUTINE + $10 ; KB_RING_SIZE bytes
KB_RING_SIZE             = 32
LCD_SCREEN               = KB_RING + KB_RING_SIZE  ; 80 bytes
LCD_SCREEN_STATE         = LCD_SCREEN + 80         ; 9 bytes
KB_RING_READ             = LCD_SCREEN_STATE + 9    ; 1 byte
KB_RING_WRITE            = KB_RING_READ + 1        ; 1 byte
PENDING_KEY              = KB_RING_WRITE + 1       ; 1 byte
HAVE_PENDING_KEY         = PENDING_KEY + 1         ; 1 byte: $ff if PENDING_KEY holds a key
CP_M_LEN                 = HAVE_PENDING_KEY + 1    ; 2 bytes (start-up only)
SERVICES_RAM_END         = CP_M_LEN + 2

  .org MICHAEL_ENV_BASE + $06
  jmp services_nothing_carry   ; $06 read_b: end of input
  jmp lcd_screen_write         ; $09 write_b
  jmp services_nothing         ; $0c write_d
  jmp services_exit            ; $0f exit
  jmp services_zero            ; $12 open: no files
  jmp services_nothing         ; $15 close
  jmp services_nothing_carry   ; $18 read: end of file
  jmp services_argc            ; $1b argc: no arguments (and start-up)
  jmp services_zero            ; $1e argv
  jmp services_zero            ; $21 openout: no files
  jmp services_nothing         ; $24 write
  jmp services_con_read        ; $27 con_read
  jmp lcd_screen_flush         ; $2a con_flush
  jmp services_con_ready       ; $2d con_ready
  jmp services_term_rows       ; $30 term_rows
  jmp services_term_cols       ; $33 term_cols
  jmp services_nothing_carry   ; $36 serial_read: nothing
  jmp services_nothing_carry   ; $39 serial_write: not accepted
  jmp services_zero            ; $3c opendir: no directories
  jmp services_zero            ; $3f wait_ready: time passed
  jmp lcd_screen_goto          ; $42 scr_goto
  jmp lcd_screen_clear         ; $45 scr_clear
  jmp lcd_screen_clear_eol     ; $48 scr_clear_eol
  jmp lcd_screen_cursor_on     ; $4b scr_cursor_on
  jmp lcd_screen_cursor_off    ; $4e scr_cursor_off
  jmp lcd_screen_nothing       ; $51 scr_reverse
  jmp lcd_screen_nothing       ; $54 scr_normal
  jmp lcd_screen_region        ; $57 scr_region
  jmp lcd_screen_region_reset  ; $5a scr_region_reset
  jmp lcd_screen_insert        ; $5d scr_insert
  jmp lcd_screen_delete        ; $60 scr_delete
  jmp lcd_screen_scroll_up     ; $63 scr_scroll_up
  jmp lcd_screen_scroll_down   ; $66 scr_scroll_down

  .include delay_routines.inc
  .include initialize_machine_v2.inc
EXTEND_CHARACTER_SET = 1
  .include display_routines.inc
  .include lcd_screen.inc
  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE = kb_ring_initialize
KB_BUFFER_WRITE      = kb_ring_write
KB_BUFFER_READ       = kb_ring_read
  .include keyboard_driver.inc
  .include keyboard_keys.inc


services_nothing_carry:
  sec
services_nothing:
  rts

services_zero:
  lda #0
  rts

services_term_rows:
  lda #DISPLAY_HEIGHT
  rts

services_term_cols:
  lda #DISPLAY_WIDTH
  rts

services_exit:
  jsr lcd_screen_flush
  stp


; argc: no arguments. The first call sets up the VIA, the LCD and the
; keyboard
services_argc:
  lda services_started
  bne services_no_arguments
  dec services_started
  phx
  phy
  jmp initialize_machine          ; Sets up the VIA's ports, then jumps to program_start
program_start:
  jsr reset_display
  jsr lcd_screen_initialize
  jsr lcd_screen_flush
  stz HAVE_PENDING_KEY
  jsr keyboard_initialize
  ply
  plx
services_no_arguments:
  lda #0
  rts

services_started:
  .byte 0


; con_ready: A = $ff if a key is waiting, else $00 (after showing the
; screen: the editor has nothing more to draw for now)
; On exit X, Y are preserved
services_con_ready:
  lda HAVE_PENDING_KEY
  bne .ready
  jsr keys_get
  bcs .none
  sta PENDING_KEY
  lda #$ff
  sta HAVE_PENDING_KEY
.ready:
  rts
.none:
  jsr lcd_screen_flush
  lda #0
  rts

; con_read: the next key, waiting for one (after showing the screen)
; On exit X, Y are preserved
services_con_read:
  lda HAVE_PENDING_KEY
  bne .pending
  jsr lcd_screen_flush
.wait:
  jsr keys_get
  bcs .wait
  rts
.pending:
  stz HAVE_PENDING_KEY
  lda PENDING_KEY
  rts


; The keyboard driver's buffer: a ring of KB_RING_SIZE bytes (a power of 2)

kb_ring_initialize:
  stz KB_RING_READ
  stz KB_RING_WRITE
  rts

; On entry A = byte to write
; On exit  C set if the ring was full; A, X, Y are preserved
kb_ring_write:
  phx
  pha
  ldx KB_RING_WRITE
  sta KB_RING, X
  inx
  txa
  and #KB_RING_SIZE - 1
  cmp KB_RING_READ
  sec
  beq .done                     ; Full: the byte is not kept
  sta KB_RING_WRITE
  clc
.done:
  pla
  plx
  rts

; On exit C set if the ring was empty, else A = the byte; X, Y are preserved
kb_ring_read:
  phx
  ldx KB_RING_READ
  cpx KB_RING_WRITE
  sec
  beq .done
  lda KB_RING, X
  pha
  inx
  txa
  and #KB_RING_SIZE - 1
  sta KB_RING_READ
  pla
  clc
.done:
  plx
  rts

services_end:

  .if services_end > INTERRUPT_ROUTINE
  .error "The services run into the interrupt page"
  .endif
  .if SERVICES_RAM_END > MICHAEL_EDITOR_SPARE
  .error "The services' RAM runs into the editor's (MICHAEL_EDITOR_SPARE)"
  .endif
