; Starts the editor on the graphic display (editor-michael-upload.sh --graphic): chooses the screen, then
; sets the scroll region to the editor's text rows, leaving the status bar outside it. Uploaded with the
; editor, built by editor/michael_image.py. Runs from zero page, which the editor then takes over.
  .include michael_rom.inc

EDITOR_START  = $0200               ; michael_image.LOAD
TEXT_ROWS     = 19                  ; term_rows - 1: the status bar is the last row

  .org $0010
  lda #1
  jsr SVC_SCREEN_SELECT
  bcs .start                        ; no FPGA with text mode: the LCD, as it is
  jsr SVC_ARGC                      ; starts the screen
  lda #1
  ldy #TEXT_ROWS
  jsr SVC_SCR_REGION
.start:
  jmp EDITOR_START
