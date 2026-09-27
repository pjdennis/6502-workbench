; The environment of 17/environment.asm for the editor's define:michael
; build: the same vectors, at the Michael services' base (the layout they
; share). michael_tests.py checks the two lists match.
  .include ../../firmware/boards/michael/michael_editor_layout.inc
ENV_BASE = MICHAEL_ENV_BASE

read_b    = ENV_BASE + $06
write_b   = ENV_BASE + $09
write_d   = ENV_BASE + $0C
exit      = ENV_BASE + $0F
open      = ENV_BASE + $12
close     = ENV_BASE + $15
read      = ENV_BASE + $18
argc      = ENV_BASE + $1B
argv      = ENV_BASE + $1E
openout   = ENV_BASE + $21
write     = ENV_BASE + $24
con_read  = ENV_BASE + $27
con_flush = ENV_BASE + $2A
con_ready = ENV_BASE + $2D
term_rows = ENV_BASE + $30
term_cols = ENV_BASE + $33
serial_read  = ENV_BASE + $36
serial_write = ENV_BASE + $39
opendir      = ENV_BASE + $3C
wait_ready   = ENV_BASE + $3F
scr_goto         = ENV_BASE + $42
scr_clear        = ENV_BASE + $45
scr_clear_eol    = ENV_BASE + $48
scr_cursor_on    = ENV_BASE + $4B
scr_cursor_off   = ENV_BASE + $4E
scr_reverse      = ENV_BASE + $51
scr_normal       = ENV_BASE + $54
scr_region       = ENV_BASE + $57
scr_region_reset = ENV_BASE + $5A
scr_insert       = ENV_BASE + $5D
scr_delete       = ENV_BASE + $60
scr_scroll_up    = ENV_BASE + $63
scr_scroll_down  = ENV_BASE + $66
CON_EOF   = $01
DIR_ENTRY_DIR      = $01
DIR_ENTRY_READONLY = $02
