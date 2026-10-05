; The editor's environment (asm/17/environment.asm, the direct_io build's) on
; Michael, behind the entry points of michael_rom.inc: the 20x4 LCD as the screen (or, chosen with
; SVC_SCREEN_SELECT, the graphic display: michael_graphic_screen.inc, which the ROM includes) and the PS/2
; keyboard for input. write_b and the scr_* calls draw on a copy of the screen that goes to the
; LCD when the program waits for a key or flushes (lcd_screen.inc); con_read and con_ready give
; keys as the editor's key codes (keyboard_keys.inc); term_rows and term_cols are 4 and 20; there
; are no files or arguments. The keyboard and the screen start separately (SVC_KEYBOARD_START,
; SVC_SCREEN_START) or together (SVC_START, and argc, the editor's first call), each setting up
; the VIA's ports if nothing has yet; michael_rom.inc says what RAM each then uses.
;
; Requires, before the include: .org SVC_BASE + $06, base_config_v2.inc, and
;   SERVICES_EXIT - where exit goes, after showing the screen

  .include michael_rom.inc

STARTED_PORTS            = %00000001 ; ROM_STARTED bits
STARTED_KEYBOARD         = %00000010
STARTED_SCREEN           = %00000100

; Zero page
KB_ZERO_PAGE_BASE        = ROM_ZP_KEYBOARD
CREATE_CHARACTER_PARAM   = ROM_ZP_SCRATCH

; The keyboard's RAM
KB_RING_READ             = ROM_RAM_KEYBOARD        ; 1 byte
KB_RING_WRITE            = KB_RING_READ + 1        ; 1 byte
PENDING_KEY              = KB_RING_WRITE + 1       ; 1 byte
HAVE_PENDING_KEY         = PENDING_KEY + 1         ; 1 byte: $ff if PENDING_KEY holds a key
KB_RING                  = HAVE_PENDING_KEY + 1    ; KB_RING_SIZE bytes
KB_RING_SIZE             = 32

; The screen's RAM
LCD_SCREEN               = ROM_RAM_SCREEN          ; 80 bytes
LCD_SCREEN_STATE         = LCD_SCREEN + 80         ; 9 bytes

  .if KB_RING + KB_RING_SIZE > ROM_RAM_SCREEN
  fail "The keyboard's RAM runs into the screen's (michael_rom.inc)"
  .endif
  .if LCD_SCREEN_STATE + 9 > ROM_SCREEN
  fail "The screen's RAM runs into ROM_SCREEN (michael_rom.inc)"
  .endif

; A screen call to the LCD's routine, or the graphic screen's when that's chosen (ROM_SCREEN bit 7)
  .macro screen,lcd,graphic
  bit ROM_SCREEN
  bpl * + 5                       ; Over the jmp
  jmp \graphic
  jmp \lcd
  .endm

; The vector table, at the includer's .org SVC_BASE + $06 (michael_rom.inc)
  .macro vector,address,target
  .if * != \address
  fail "a service vector is out of place"
  .endif
  jmp \target
  .endm

  vector SVC_READ_B          , services_nothing_carry   ; read_b: end of input
  vector SVC_WRITE_B         , screen_write             ; write_b
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
  vector SVC_CON_FLUSH       , services_show            ; con_flush
  vector SVC_CON_READY       , services_con_ready       ; con_ready
  vector SVC_TERM_ROWS       , screen_rows              ; term_rows
  vector SVC_TERM_COLS       , screen_cols              ; term_cols
  vector SVC_SERIAL_READ     , services_nothing_carry   ; serial_read: nothing
  vector SVC_SERIAL_WRITE    , services_nothing_carry   ; serial_write: not accepted
  vector SVC_OPENDIR         , services_zero            ; opendir: no directories
  vector SVC_WAIT_READY      , services_zero            ; wait_ready: time passed
  vector SVC_SCR_GOTO        , screen_goto              ; scr_goto
  vector SVC_SCR_CLEAR       , screen_clear             ; scr_clear
  vector SVC_SCR_CLEAR_EOL   , screen_clear_eol         ; scr_clear_eol
  vector SVC_SCR_CURSOR_ON   , screen_cursor_on         ; scr_cursor_on
  vector SVC_SCR_CURSOR_OFF  , screen_cursor_off        ; scr_cursor_off
  vector SVC_SCR_REVERSE     , screen_reverse           ; scr_reverse
  vector SVC_SCR_NORMAL      , screen_normal            ; scr_normal
  vector SVC_SCR_REGION      , screen_region            ; scr_region
  vector SVC_SCR_REGION_RESET, screen_region_reset      ; scr_region_reset
  vector SVC_SCR_INSERT      , screen_insert            ; scr_insert
  vector SVC_SCR_DELETE      , screen_delete            ; scr_delete
  vector SVC_SCR_SCROLL_UP   , screen_scroll_up         ; scr_scroll_up
  vector SVC_SCR_SCROLL_DOWN , screen_scroll_down       ; scr_scroll_down
  vector SVC_SCR_INSERT_LINES, screen_insert_lines      ; scr_insert_lines
  vector SVC_SCR_DELETE_LINES, screen_delete_lines      ; scr_delete_lines
  .rept (SVC_START - SVC_SCR_DELETE_LINES) / 3 - 1       ; room for more
  jmp services_nothing
  .endr
  vector SVC_START           , services_start           ; Michael's own: start the services
  vector SVC_LCD_COMMAND     , display_command          ; LCD command in A
  vector SVC_LCD_CHARACTER   , display_character        ; character in A at the LCD's cursor
  vector SVC_DELAY           , delay_10_thousandths     ; wait A x 100 us
  vector SVC_KEYBOARD_START  , services_keyboard_start
  vector SVC_SCREEN_START    , services_screen_start
  vector SVC_IRQ             , rom_interrupt
  vector SVC_SCREEN_SELECT   , services_screen_select

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

; The screen calls: the LCD's, or the graphic screen's
screen_write:        screen lcd_screen_write, graphic_write
screen_rows:         screen services_term_rows, graphic_rows
screen_cols:         screen services_term_cols, graphic_cols
screen_goto:         screen lcd_screen_goto, graphic_goto
screen_clear:        screen lcd_screen_clear, graphic_clear
screen_clear_eol:    screen lcd_screen_clear_eol, graphic_clear_eol
screen_cursor_on:    screen lcd_screen_cursor_on, graphic_cursor_on
screen_cursor_off:   screen lcd_screen_cursor_off, graphic_cursor_off
screen_reverse:      screen lcd_screen_nothing, graphic_reverse
screen_normal:       screen lcd_screen_nothing, graphic_normal
screen_region:       screen lcd_screen_region, graphic_region
screen_region_reset: screen lcd_screen_region_reset, graphic_region_reset
screen_insert:       screen lcd_screen_insert, graphic_insert
screen_delete:       screen lcd_screen_delete, graphic_delete
screen_scroll_up:    screen lcd_screen_scroll_up, graphic_scroll_up
screen_scroll_down:  screen lcd_screen_scroll_down, graphic_scroll_down
screen_insert_lines: screen lcd_screen_insert_lines, graphic_insert_lines
screen_delete_lines: screen lcd_screen_delete_lines, graphic_delete_lines

; SVC_SCREEN_SELECT: A = 0 the LCD, 1 the graphic screen; C set (and the LCD kept) if there's no FPGA
; with text mode. A screen already started gives way to the chosen one, started at once
; On exit A is not preserved; X, Y are
services_screen_select:
  cmp #0
  beq .chosen                     ; A = 0: the LCD
  jsr graphic_present
  bcs .done                       ; No text mode: the LCD stays
  lda #$80
.chosen:
  cmp ROM_SCREEN
  beq .same
  sta ROM_SCREEN
  lda #STARTED_SCREEN
  trb ROM_STARTED
  beq .same                       ; Not started yet: the start call will
  jsr services_screen_start
.same:
  clc
.done:
  rts

services_exit:
  jsr services_show
  jmp SERVICES_EXIT

; Show the screen on the LCD, if it has started (the graphic screen shows itself)
; On exit A, X, Y are preserved
services_show:
  pha
  lda ROM_STARTED
  and #STARTED_SCREEN
  beq .not_started
  bit ROM_SCREEN
  bmi .not_started
  jsr lcd_screen_flush
.not_started:
  pla
  rts


; argc: no arguments. The first call starts the services
services_argc:
  jsr services_start
  lda #0
  rts

; Start the keyboard and the screen
; On exit A is not preserved; X, Y are
services_start:
  jsr services_keyboard_start
  ; fall through

; Start the screen, the first time: the LCD, cleared, and its copy in RAM; or the graphic screen
; On exit A is not preserved; X, Y are
services_screen_start:
  lda #STARTED_SCREEN
  jsr services_first_time
  bne .started
  bit ROM_SCREEN
  bpl .lcd
  jmp graphic_start
.lcd:
  phx
  phy
  jsr reset_display
  jsr lcd_screen_initialize
  jsr lcd_screen_flush
  ply
  plx
.started:
  rts

; Start the keyboard, the first time: its handler behind ROM_IRQ_JMP, interrupts enabled
; On exit A is not preserved; X, Y are
services_keyboard_start:
  lda #STARTED_KEYBOARD
  jsr services_first_time
  bne .started
  phx
  phy
  lda #$4c                        ; jmp SVC_IRQ, where the IRQ vector points
  sta ROM_IRQ_JMP
  lda #<SVC_IRQ
  sta ROM_IRQ_JMP + 1
  lda #>SVC_IRQ
  sta ROM_IRQ_JMP + 2
  stz HAVE_PENDING_KEY
  jsr keyboard_initialize
  ply
  plx
.started:
  rts

; On entry A = the ROM_STARTED bit of the part starting
; On exit  Z clear if it had already started; else the bit is set, the VIA's ports are set up
;          if they weren't, and Z is set
services_first_time:
  bit ROM_STARTED
  bne .done
  tsb ROM_STARTED
  lda #STARTED_PORTS
  tsb ROM_STARTED
  bne .ports_done
  initialize_michael_ports
  lda #10                         ; 1 ms: the port setup pulses the keyboard's clock low, and the
  jsr delay_10_thousandths        ; frame detector holds CA2 low for ~100 us after, so a command
.ports_done:                      ; sent sooner would never see it fall
  lda #0                          ; Z set
.done:
  rts

; What reset and the loader do before a program runs: nothing started, LCD routines disabling
; interrupts
services_reset:
  stz ROM_STARTED
  stz ROM_FLAGS
  stz ROM_SCREEN                  ; The LCD
  rts


; The ROM's interrupt handler (SVC_IRQ): each service that uses interrupts checks for its own
rom_interrupt:
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
  jsr services_show
  lda #0
  rts

; con_read: the next key, waiting for one (after showing the screen)
; On exit X, Y are preserved
services_con_read:
  lda HAVE_PENDING_KEY
  bne .pending
  jsr services_show
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
