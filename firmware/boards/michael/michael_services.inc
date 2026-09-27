; The asm2 editor's environment (toolchain/asm2/17/environment.asm, the direct_io build's) on
; Michael: the 20x4 LCD as the screen and the PS/2 keyboard for input, behind the vector table
; of michael_rom_vectors.inc. write_b and the scr_* calls draw on a copy of the screen that goes to
; the LCD when the program waits for a key or flushes (lcd_screen.inc); con_read and con_ready
; give keys as the editor's key codes (keyboard_keys.inc); term_rows and term_cols are 4 and 20;
; there are no files or arguments. argc, the editor's first call, starts the services
; (SVC_START does the same for other programs): the VIA's ports, the LCD and the keyboard. Zero
; page from $F0 up and the interrupt page up to MICHAEL_EDITOR_SPARE are theirs from then on.
;
; Requires, before the include: .org SVC_BASE + $06 (michael_rom_vectors.inc), base_config_v2.inc,
;   SERVICES_STARTED - 1 byte, 0 until the services start
;   SERVICES_EXIT    - where exit goes, after showing the screen

  .include michael_rom_vectors.inc
  .include michael_editor_layout.inc

; Zero page
KB_ZERO_PAGE_BASE        = $f0 ; 10 bytes
CREATE_CHARACTER_PARAM   = $fa ; 2 bytes (start-up only)

; RAM in the interrupt page, after the jmp to the keyboard's handler
  .ifndef INTERRUPT_ROUTINE
INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET
  .endif
KB_RING                  = INTERRUPT_ROUTINE + $10 ; KB_RING_SIZE bytes
KB_RING_SIZE             = 32
LCD_SCREEN               = KB_RING + KB_RING_SIZE  ; 80 bytes
LCD_SCREEN_STATE         = LCD_SCREEN + 80         ; 9 bytes
KB_RING_READ             = LCD_SCREEN_STATE + 9    ; 1 byte
KB_RING_WRITE            = KB_RING_READ + 1        ; 1 byte
PENDING_KEY              = KB_RING_WRITE + 1       ; 1 byte
HAVE_PENDING_KEY         = PENDING_KEY + 1         ; 1 byte: $ff if PENDING_KEY holds a key
SERVICES_RAM_END         = HAVE_PENDING_KEY + 1

; The vector table, at the includer's .org SVC_BASE + $06 (michael_rom_vectors.inc)
  .macro vector,address,target
  .if * != \address
  fail "a service vector is out of place"
  .endif
  jmp \target
  .endm

  vector SVC_READ_B          , services_nothing_carry   ; read_b: end of input
  vector SVC_WRITE_B         , lcd_screen_write         ; write_b
  vector SVC_WRITE_D         , services_nothing         ; write_d
  vector SVC_EXIT            , services_exit            ; exit
  vector SVC_OPEN            , services_zero            ; open: no files
  vector SVC_CLOSE           , services_nothing         ; close
  vector SVC_READ            , services_nothing_carry   ; read: end of file
  vector SVC_ARGC            , services_argc            ; argc: no arguments (and start-up)
  vector SVC_ARGV            , services_zero            ; argv
  vector SVC_OPENOUT         , services_zero            ; openout: no files
  vector SVC_WRITE           , services_nothing         ; write
  vector SVC_CON_READ        , services_con_read        ; con_read
  vector SVC_CON_FLUSH       , lcd_screen_flush         ; con_flush
  vector SVC_CON_READY       , services_con_ready       ; con_ready
  vector SVC_TERM_ROWS       , services_term_rows       ; term_rows
  vector SVC_TERM_COLS       , services_term_cols       ; term_cols
  vector SVC_SERIAL_READ     , services_nothing_carry   ; serial_read: nothing
  vector SVC_SERIAL_WRITE    , services_nothing_carry   ; serial_write: not accepted
  vector SVC_OPENDIR         , services_zero            ; opendir: no directories
  vector SVC_WAIT_READY      , services_zero            ; wait_ready: time passed
  vector SVC_SCR_GOTO        , lcd_screen_goto          ; scr_goto
  vector SVC_SCR_CLEAR       , lcd_screen_clear         ; scr_clear
  vector SVC_SCR_CLEAR_EOL   , lcd_screen_clear_eol     ; scr_clear_eol
  vector SVC_SCR_CURSOR_ON   , lcd_screen_cursor_on     ; scr_cursor_on
  vector SVC_SCR_CURSOR_OFF  , lcd_screen_cursor_off    ; scr_cursor_off
  vector SVC_SCR_REVERSE     , lcd_screen_nothing       ; scr_reverse
  vector SVC_SCR_NORMAL      , lcd_screen_nothing       ; scr_normal
  vector SVC_SCR_REGION      , lcd_screen_region        ; scr_region
  vector SVC_SCR_REGION_RESET, lcd_screen_region_reset  ; scr_region_reset
  vector SVC_SCR_INSERT      , lcd_screen_insert        ; scr_insert
  vector SVC_SCR_DELETE      , lcd_screen_delete        ; scr_delete
  vector SVC_SCR_SCROLL_UP   , lcd_screen_scroll_up     ; scr_scroll_up
  vector SVC_SCR_SCROLL_DOWN , lcd_screen_scroll_down   ; scr_scroll_down
  vector SVC_START           , services_start           ; Michael's own: start the services
  vector SVC_LCD_COMMAND     , display_command          ; LCD command in A
  vector SVC_LCD_CHARACTER   , display_character        ; character in A at the LCD's cursor
  vector SVC_DELAY           , delay_10_thousandths     ; wait A x 100 us

  .include delay_routines.inc
  .include michael_ports.inc
  .ifndef EXTEND_CHARACTER_SET           ; '~' and '\' as custom characters
EXTEND_CHARACTER_SET = 1
  .endif
  .include display_routines.inc
  .include lcd_screen.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE = kb_ring_initialize
KB_BUFFER_WRITE      = kb_ring_write
KB_BUFFER_READ       = kb_ring_read
KB_NO_INTERRUPT_HANDLER = 1                ; The services put a jmp to theirs where the vector points
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
  jmp SERVICES_EXIT


; argc: no arguments. The first call starts the services
services_argc:
  jsr services_start
  lda #0
  rts

; Set up the VIA, the LCD and the keyboard, the first time
; On exit A is not preserved; X, Y are
services_start:
  lda SERVICES_STARTED
  bne .started
  dec SERVICES_STARTED
  phx
  phy
  initialize_michael_ports
  lda #$4c                        ; jmp services_interrupt, where the IRQ vector points
  sta INTERRUPT_ROUTINE
  lda #<services_interrupt
  sta INTERRUPT_ROUTINE + 1
  lda #>services_interrupt
  sta INTERRUPT_ROUTINE + 2
  jsr reset_display
  jsr lcd_screen_initialize
  jsr lcd_screen_flush
  stz HAVE_PENDING_KEY
  jsr keyboard_initialize
  ply
  plx
.started:
  rts


services_interrupt:
  pha
  jsr handle_keyboard_interrupt
  pla
  rti


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

  .if SERVICES_RAM_END > MICHAEL_EDITOR_SPARE
  fail "The services' RAM runs into the editor's (MICHAEL_EDITOR_SPARE)"
  .endif
