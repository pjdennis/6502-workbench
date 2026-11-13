; Addressing mode constants
MODE_NONE = $00   ; Implied (no operand)
MODE_ACC  = $01   ; Accumulator
MODE_IMM  = $02   ; Immediate
MODE_ZP   = $03   ; Zero page
MODE_ZPX  = $04   ; Zero page, X
MODE_ZPY  = $05   ; Zero page, Y
MODE_ABS  = $06   ; Absolute
MODE_ABSX = $07   ; Absolute, X
MODE_ABSY = $08   ; Absolute, Y
MODE_INDX = $09   ; Indirect, X - ($zp,X)
MODE_INDY = $0A   ; Indirect, Y - ($zp),Y
MODE_REL  = $0B   ; Relative (branches)
MODE_IND  = $0C   ; Indirect - JMP ($xxxx)

HT_KEY = TOKEN
HT_VL  = HEX2
HT_VH  = HEX1
  .include hash_table.asm


init_heap
  LDA #<HEAP
  STA MEMPL
  LDA #>HEAP
  STA MEMPH
  RTS


; On entry Y contains the amount to advance
; On exit MEMPL;MEMPH is incremented by Y
;         Y = 0
;         X is preserved
;         A is not preserved
advance_heap
  TYA
  LDY #$00
  CLC
  ADC MEMPL
  STA MEMPL
  TYA
  ADC MEMPH
  STA MEMPH
  RTS


; Store hash value at current heap location and advance heap
; On entry HT_VL;HT_VH contains the value to store
;          MEMPL;MEMPH points to where value should be stored
; On exit MEMPL;MEMPH advanced past the value
;         Y = 0
;         X is preserved
;         A is not preserved
store_hash_value
  LDY #$00
  LDA HT_VL
  STA (MEMPL),Y
  INY
  LDA HT_VH
  STA (MEMPL),Y
  INY
  JMP advance_heap     ; Tail call


select_instruction_hash_table
  LDA #$00
  STA IS_LOCAL_LABEL       ; Clear local label flag for instruction lookup
  LDA #<IHASHTAB
  STA HTPL
  LDA #>IHASHTAB
  STA HTPH
  RTS
