; Michael's ROM (michael_rom.s) as programs see it: the entry points of its services
; (michael_services.inc) and the RAM they use. This file is the source of truth: the ROM checks
; that each entry is where this says.
;
; Entry points are 3-byte jmps. The asm17 environment's are at the offsets of
; asm/17/environment.asm (the editor uses that file); Michael's own follow.
;
; RAM: the loader uses nothing that lasts once a program runs. A program that calls the LCD
; routines (SVC_LCD_*, and the services') must leave ROM_FLAGS alone; one that starts the
; keyboard or the screen must also leave that part's RAM alone, from the start call on.
;
; Interrupts: starting the keyboard puts a jmp to SVC_IRQ at ROM_IRQ_JMP, where the IRQ vector
; points, and enables interrupts. A program with its own interrupts can, after that, point
; the jmp at its own handler, which ends by restoring the registers and jumping to SVC_IRQ.

  .ifndef SVC_BASE
SVC_BASE             = $F000
  .endif

SVC_READ_B           = SVC_BASE + $06
SVC_WRITE_B          = SVC_BASE + $09
SVC_WRITE_D          = SVC_BASE + $0C
SVC_EXIT             = SVC_BASE + $0F
SVC_OPEN             = SVC_BASE + $12
SVC_CLOSE            = SVC_BASE + $15
SVC_READ             = SVC_BASE + $18
SVC_ARGC             = SVC_BASE + $1B
SVC_ARGV             = SVC_BASE + $1E
SVC_OPENOUT          = SVC_BASE + $21
SVC_WRITE            = SVC_BASE + $24
SVC_CON_READ         = SVC_BASE + $27
SVC_CON_FLUSH        = SVC_BASE + $2A
SVC_CON_READY        = SVC_BASE + $2D
SVC_TERM_ROWS        = SVC_BASE + $30
SVC_TERM_COLS        = SVC_BASE + $33
SVC_SERIAL_READ      = SVC_BASE + $36
SVC_SERIAL_WRITE     = SVC_BASE + $39
SVC_OPENDIR          = SVC_BASE + $3C
SVC_WAIT_READY       = SVC_BASE + $3F
SVC_SCR_GOTO         = SVC_BASE + $42
SVC_SCR_CLEAR        = SVC_BASE + $45
SVC_SCR_CLEAR_EOL    = SVC_BASE + $48
SVC_SCR_CURSOR_ON    = SVC_BASE + $4B
SVC_SCR_CURSOR_OFF   = SVC_BASE + $4E
SVC_SCR_REVERSE      = SVC_BASE + $51
SVC_SCR_NORMAL       = SVC_BASE + $54
SVC_SCR_REGION       = SVC_BASE + $57
SVC_SCR_REGION_RESET = SVC_BASE + $5A
SVC_SCR_INSERT       = SVC_BASE + $5D
SVC_SCR_DELETE       = SVC_BASE + $60
SVC_SCR_SCROLL_UP    = SVC_BASE + $63
SVC_SCR_SCROLL_DOWN  = SVC_BASE + $66
SVC_SCR_INSERT_LINES = SVC_BASE + $69
SVC_SCR_DELETE_LINES = SVC_BASE + $6C
; (up to $8D: room for more of the environment's; each does nothing)
; Michael's own. All preserve X and Y
SVC_START            = SVC_BASE + $90 ; Start the keyboard and the screen (argc does, the first time)
SVC_LCD_COMMAND      = SVC_BASE + $93 ; Send the LCD command in A (no start needed)
SVC_LCD_CHARACTER    = SVC_BASE + $96 ; Write the character in A at the LCD's cursor (no start needed)
SVC_DELAY            = SVC_BASE + $99 ; Wait A times 100 microseconds
SVC_KEYBOARD_START   = SVC_BASE + $9C ; Start the keyboard: con_read, con_ready; enables interrupts
SVC_SCREEN_START     = SVC_BASE + $9F ; Start the screen: write_b, con_flush, scr_*
SVC_IRQ              = SVC_BASE + $A2 ; The ROM's interrupt handler (ends with rti)
SVC_SCREEN_SELECT    = SVC_BASE + $A5 ; The screen: A = 0 the LCD, 1 the graphic display (the FPGA's text
                                      ; mode, 20 by 20); C set, and the LCD kept, if no FPGA with text mode
                                      ; answers. Choose before starting the screen, or the chosen one starts
                                      ; at once. The loader sets the LCD again before each program
SVC_END              = SVC_BASE + $A8

; Zero page
ROM_ZP_KEYBOARD      = $F0 ; $F0-$F9: the keyboard's, from SVC_KEYBOARD_START
ROM_ZP_SCRATCH       = $FA ; $FA-$FB: used while the screen starts (and at reset)
ROM_FLAGS            = $FC ; Bit 7 set: the LCD routines leave interrupts on (the loader, while
                           ; receiving); clear: they disable them around each strobe. Other bits
                           ; reserved. Cleared before a program runs
; $FD-$FF: free

; RAM, in the interrupt page (the loader's receive handler is there while it uploads)
ROM_IRQ_JMP          = $3F00 ; 3 bytes: jmp, where the IRQ vector points (from SVC_KEYBOARD_START)
ROM_STARTED          = $3F03 ; 1 byte: which parts have started (cleared before a program runs)
ROM_RAM_KEYBOARD     = $3F04 ; The keyboard's, from SVC_KEYBOARD_START...
ROM_RAM_SCREEN       = $3F28 ; ...the screen's, from SVC_SCREEN_START...
ROM_SCREEN           = $3F81 ; 1 byte: bit 7 set: the graphic screen (from SVC_SCREEN_SELECT)
ROM_PUTTING          = $3F82 ; 1 byte: bit 7 set: the FPGA bus's last command was PUT (the graphic screen's)
ROM_RAM_END          = $3F83 ; ...up to here
