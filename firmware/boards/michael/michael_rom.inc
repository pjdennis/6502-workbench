; The service entry points of Michael's ROM (michael_services.inc), for vasm programs: the asm2
; environment's vectors (toolchain/asm2/17/environment.asm, at the same offsets; the editor uses
; that file) and Michael's own after them. Each is a 3-byte jmp; see michael_services.inc for
; what they do. SVC_BASE is $F000 unless defined first.

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
; Michael's own
SVC_START            = SVC_BASE + $69 ; Start the LCD and keyboard (argc does, the first time)
SVC_LCD_COMMAND      = SVC_BASE + $6C ; Send the LCD command in A
SVC_LCD_CHARACTER    = SVC_BASE + $6F ; Write the character in A at the LCD's cursor
SVC_DELAY            = SVC_BASE + $72 ; Wait A times 100 microseconds
SVC_END              = SVC_BASE + $75
