; Memory map: the buffers at fixed addresses (TEXT_BUF floats after the
; code, see the end of this file). TEXT_END, LINE_TBL and YANK_BUF are
; page-aligned. MARK_SAVE (mark.asm) is MARK_TBL + $80, and SEARCH_BUF
; holds a pattern as long as CMD_BUF holds.
  .ifdef michael
; Michael: 16 KB of RAM from $0200, shared with the ROM's services, which
; keep $3F00 up to MICHAEL_EDITOR_SPARE (michael_editor_layout.inc)
  .include ../../firmware/boards/michael/michael_editor_layout.inc
BATCH_BUF     = $0100   ; Below the stack, which stays above $0154
STATUS_SHADOW = $0120   ; The status bar's text: a row (52 bytes here)
TEXT_END      = $3900   ; The text buffer runs from the end of the code
MARK_TBL      = $3900   ; Marks a-z; MARK_SAVE at $3980
LINE_TBL      = $3A00
LINE_TBL_END  = $3C00
YANK_BUF      = $3C00
YANK_LIMIT    = $3E00
UNDO_DATA_BUF = $3E00
CMD_BUF       = MICHAEL_EDITOR_SPARE
CMD_BUF_END   = MICHAEL_EDITOR_SPARE + $38
SEARCH_BUF    = MICHAEL_EDITOR_SPARE + $38  ; To the end of RAM
  .else
SEARCH_BUF    = $0200   ; Search pattern and its null (128 bytes)
CMD_BUF       = $0300   ; Command buffer, up to CMD_BUF_END
CMD_BUF_END   = $0380
STATUS_SHADOW = $0380   ; The status bar's text (status_build), 128 bytes
TEXT_END      = $D600   ; End of the text buffer's space
BATCH_BUF     = $D600   ; Batch insert staging buffer (BATCH_MAX bytes)
MARK_TBL      = $D620   ; Marks a-z: 26 entries x 2 bytes; MARK_SAVE at $D6A0
UNDO_DATA_BUF = $D700   ; Undo data (256 bytes, page-aligned)
LINE_TBL      = $D800   ; Line pointer table (2 bytes per entry), up to
LINE_TBL_END  = $E000   ; LINE_TBL_END
YANK_BUF      = $E000   ; Yank buffer (page-aligned), up to YANK_LIMIT
YANK_LIMIT    = $F000
  .endif
