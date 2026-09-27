; Memory map: the buffers at fixed addresses (TEXT_BUF floats after the
; code, see the end of this file). TEXT_END, LINE_TBL and YANK_BUF are
; page-aligned.
  .ifdef michael
; Michael: 16 KB of RAM, shared with the services (environment.asm,
; michael_editor_layout.inc)
BATCH_BUF     = $0100   ; Below the stack, which stays above $0154
MARK_TBL      = $0120
YANK_BUF      = $0200
YANK_LIMIT    = $0300
UNDO_DATA_BUF = $0300
TEXT_END      = $3400
LINE_TBL      = $3400
LINE_TBL_END  = MICHAEL_ENV_BASE + $06
FNAME_BUF     = MICHAEL_EDITOR_SPARE         ; 16 bytes
CMD_BUF       = MICHAEL_EDITOR_SPARE + $10
CMD_BUF_END   = MICHAEL_EDITOR_SPARE + $40
SEARCH_BUF    = MICHAEL_EDITOR_SPARE + $40
SEARCH_LIMIT  = MICHAEL_EDITOR_SPARE + $70
  .else
FNAME_BUF     = $0200   ; Filename buffer (256 bytes)
CMD_BUF       = $0300   ; Command buffer, up to CMD_BUF_END
CMD_BUF_END   = $0400
TEXT_END      = $D600   ; End of the text buffer's space
BATCH_BUF     = $D600   ; Batch insert staging buffer (BATCH_MAX bytes)
MARK_TBL      = $D620   ; Marks a-z: 26 entries x 2 bytes
SEARCH_BUF    = $D654   ; Search pattern, up to SEARCH_LIMIT
SEARCH_LIMIT  = $D700
UNDO_DATA_BUF = $D700   ; Undo data (256 bytes, page-aligned)
LINE_TBL      = $D800   ; Line pointer table (2 bytes per entry), up to
LINE_TBL_END  = $E000   ; LINE_TBL_END
YANK_BUF      = $E000   ; Yank buffer (page-aligned), up to YANK_LIMIT
YANK_LIMIT    = $F000
  .endif
