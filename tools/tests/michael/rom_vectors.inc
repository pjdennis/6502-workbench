; The ROM's service vectors under the asm17 environment's names (asm/17/environment.asm),
; for the test programs
  .include michael_rom.inc
write_b          = SVC_WRITE_B
exit             = SVC_EXIT
argc             = SVC_ARGC
con_read         = SVC_CON_READ
con_flush        = SVC_CON_FLUSH
con_ready        = SVC_CON_READY
scr_goto         = SVC_SCR_GOTO
scr_clear        = SVC_SCR_CLEAR
scr_clear_eol    = SVC_SCR_CLEAR_EOL
scr_cursor_on    = SVC_SCR_CURSOR_ON
scr_cursor_off   = SVC_SCR_CURSOR_OFF
scr_region       = SVC_SCR_REGION
scr_region_reset = SVC_SCR_REGION_RESET
scr_insert       = SVC_SCR_INSERT
scr_delete       = SVC_SCR_DELETE
scr_scroll_up    = SVC_SCR_SCROLL_UP
scr_scroll_down  = SVC_SCR_SCROLL_DOWN
scr_insert_lines = SVC_SCR_INSERT_LINES
scr_delete_lines = SVC_SCR_DELETE_LINES

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
