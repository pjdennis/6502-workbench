; Contains each byte $00-$7F exactly once in random order
scramble_table
  DATA $01 $20 $33 $1B $1C $16 $29 $1F $3A $75 $62 $42 $68 $79 $00 $52
  DATA $32 $0B $22 $77 $72 $71 $10 $59 $06 $4D $17 $37 $40 $0C $66 $21
  DATA $1E $43 $3E $30 $13 $07 $7E $44 $6C $58 $15 $1A $5A $24 $0F $7A
  DATA $7B $39 $4B $53 $70 $73 $19 $69 $55 $7D $4C $2C $7C $47 $23 $61
  DATA $56 $48 $74 $2F $76 $26 $2E $2B $6B $57 $12 $4F $25 $64 $0A $27
  DATA $50 $65 $5D $31 $2A $46 $6F $5F $67 $54 $18 $49 $05 $11 $03 $6E
  DATA $02 $0E $34 $5E $63 $08 $6D $14 $6A $0D $3B $4E $3D $60 $41 $38
  DATA $45 $7F $3F $3C $5C $2D $35 $51 $04 $28 $09 $4A $78 $1D $36 $5B


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
  LDA# <IHASHTABL
  STAZ HTLPL
  LDA# >IHASHTABL
  STAZ HTLPH
  LDA# <IHASHTABH
  STAZ HTHPL
  LDA# >IHASHTABH
  STAZ HTHPH
  RTS


init_hash_table
  LDY# $00
  TYA                  ; A <- 0
iht_loop
  STAZ(),Y HTLPL
  STAZ(),Y HTHPL
  INY
  CPY# $80
  BNE iht_loop
  RTS


; On entry TOKEN contains the token to calculate hash from
; On exit HASH contains the calculated hash value
;         X is preserved
;         A, Y are not preserved
calculate_hash
  TXA
  PHA
  LDA# $00
  STAZ HASH
  LDX# $00
ch_loop
  LDAZ,X TOKEN
  BEQ ch_done
  AND# $7F
  EORZ HASH
  TAY
  LDA,Y scramble_table
  STAZ HASH
  INX
  JMP ch_loop
ch_done
  PLA
  TAX
  RTS


; On entry HASH contains the hash value
; On exit Z set if entry is empty, clear otherwise
;         X is preserved
;         A, Y are not preserved
hash_entry_empty
  LDAZ HASH
  TAY
  LDAZ(),Y HTLPL
  BNE hee_done
  LDAZ(),Y HTHPL
hee_done
  RTS


; Load from hash table to TABPL;TABPH
; On entry HASH contains the hash value
; On exit TABPL;TABPH countains pointer corresponding to the hash value
;         X is preserved
;         A, Y are not preserved
load_hash_entry
  LDAZ HASH
  TAY
  LDAZ(),Y HTLPL
  STAZ TABPL
  LDAZ(),Y HTHPL
  STAZ TABPH
  RTS


; Store current memory pointer in hash table
; On entry HASH contains the hash code to store under
;          MEMPL;MEMPH contains the pointer to store in the hash table
; On exit X is preserved
;         A, Y are not preserved
store_hash_entry
  LDAZ HASH
  TAY
  LDAZ MEMPL
  STAZ(),Y HTLPL
  LDAZ MEMPH
  STAZ(),Y HTHPL
  RTS


; Store current memory pointer in table
; On entry TABPL;TABPH,Y points to location to store pointer
;          MEMPL;NENPL contains the pointer to store
; On exit TABPL;TABPH,Y points to the location following the stored pointer
;         X is preserved
;         A is not preserved
store_table_entry
  LDAZ MEMPL
  STAZ(),Y TABPL
  INY
  LDAZ MEMPH
  STAZ(),Y TABPL
  INY
  RTS


; On entry TOKEN contains the token to compare with
;          TABPL;TABPH points to the value to compare with
; On exit Z set if equal, unset otherwise
;         Y points to terminating 0 if equal
compare_token
  LDY# $FF
ct_loop
  INY
  LDAZ(),Y TABPL
  CMP,Y TOKEN
  BNE ct_done
  CMP# $00
  BNE ct_loop
  ; Match
ct_done
  RTS


; On entry TABPL;TABPH point to head of list of entries
;          TOKEN contains the token to find
; On exit C clear if found; set if not found
;         TABPL;TABPH,Y points to value if found
;         or to 'next' pointer if not found
find_token
ft_token_loop
  ; Store the current pointer
  LDAZ TABPL
  STAZ PL
  LDAZ TABPH
  STAZ PH
  ; Advance past 'next' pointer
  CLC
  LDA# $02
  ADCZ TABPL
  STAZ TABPL
  LDA# $00
  ADCZ TABPH
  STAZ TABPH
  ; Check for matching token
  JSR compare_token
  BNE ft_token_is_non_match
  ; Match
  INY                  ; point tab,Y to value
  CLC
  RTS
ft_token_is_non_match  ; Not a match - move to next
  ; Check if 'next' pointer is 0
  LDY# $00
  LDAZ(),Y PL
  BNE ft_not_at_end
  INY
  LDAZ(),Y PL
  BEQ ft_at_end
ft_not_at_end
  LDY# $00
  LDAZ(),Y PL
  STAZ TABPL
  INY
  LDAZ(),Y PL
  STAZ TABPH
  JMP ft_token_loop
ft_at_end
  ; point tabp,Y to the zero 'next' pointer
  LDAZ PL
  STAZ TABPL
  LDAZ PH
  STAZ TABPH
  LDY# $00
  SEC ; Carry set indicates not found
  RTS


; Stores null next pointer, token and value on heap
; and advances heap pointer
; On entry HEX1 and HEX2 contain MSB and LSB of value
;          TOKEN contains name of token
; On exit MEMPL;MEMPH points to the next free heap location
;         Y = 0
;         X is preserved
;         A is not preserved
store_token
  LDY# $00
  ; Store null pointer (pointer to next)
  LDA# $00
  STAZ(),Y MEMPL
  INY
  STAZ(),Y MEMPL
  INY
  JSR advance_heap
  ; Store token name
  LDY# $FF             ; Alternative: DEY
st_loop
  INY
  LDA,Y TOKEN
  STAZ(),Y MEMPL
  BNE st_loop
  INY
  ; Store value
  LDAZ HEX2
  STAZ(),Y MEMPL
  INY
  LDAZ HEX1
  STAZ(),Y MEMPL
  INY
  JMP advance_heap     ; Tail call


; Add TOKEN mapped to HEX2;HEX1 to hash table
; On entry TOKEN contains token
;          HEX1 and HEX2 contain MSB and LSB of value
; On exit C = 0 if added or 1 if already exists
;         A, X, Y are not preserved
hash_add
  JSR calculate_hash
  JSR hash_entry_empty
  BEQ ha_entry_empty
  JSR load_hash_entry
  JSR find_token
  BCS ha_new
  SEC
  RTS
ha_new
  JSR store_table_entry
  JMP ha_store
ha_entry_empty
  JSR store_hash_entry
ha_store
  JSR store_token
  CLC
  RTS
