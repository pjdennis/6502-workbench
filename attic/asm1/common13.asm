HT_KEY = TOKEN
HT_VL  = HEX2
HT_VH  = HEX1
  .include hash_table13.asm


init_heap
  LDA# <HEAP
  STAZ MEMPL
  LDA# >HEAP
  STAZ MEMPH
  RTS


; On entry Y contains the amount to advance
; On exit MEMPL;MEMPH is incremented by Y
;         Y = 0
;         X is preserved
;         A is not preserved
advance_heap
  TYA
  LDY# $00
  CLC
  ADCZ MEMPL
  STAZ MEMPL
  TYA
  ADCZ MEMPH
  STAZ MEMPH
  RTS


select_instruction_hash_table
  LDA# <IHASHTAB
  STAZ HTPL
  LDA# >IHASHTAB
  STAZ HTPH
  RTS
