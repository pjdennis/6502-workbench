; The environment vectors (toolchain/asm2/17/environment.asm) at the
; Michael services' base, for vasm test programs
ENV_BASE         = MICHAEL_ENV_BASE
write_b          = ENV_BASE + $09
exit             = ENV_BASE + $0f
argc             = ENV_BASE + $1b
con_read         = ENV_BASE + $27
con_flush        = ENV_BASE + $2a
con_ready        = ENV_BASE + $2d
scr_goto         = ENV_BASE + $42
scr_clear        = ENV_BASE + $45
scr_clear_eol    = ENV_BASE + $48
scr_cursor_on    = ENV_BASE + $4b
scr_cursor_off   = ENV_BASE + $4e
scr_region       = ENV_BASE + $57
scr_region_reset = ENV_BASE + $5a
scr_insert       = ENV_BASE + $5d
scr_delete       = ENV_BASE + $60
scr_scroll_up    = ENV_BASE + $63
scr_scroll_down  = ENV_BASE + $66

TEXT_PTR         = $00 ; 2 bytes

; Move to row \1, column \2 (1-based)
  .macro goto,row,col
  lda #\row
  ldy #\col
  jsr scr_goto
  .endm

; Write the string at \1
  .macro print,string
  lda #<\string
  sta TEXT_PTR
  lda #>\string
  sta TEXT_PTR + 1
  jsr print_string
  .endm
