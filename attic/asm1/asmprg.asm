write_b    = $F009

hash       = $0000
memp_l     = $0001
memp_h     = $0002
tabp_l     = $0003
tabp_h     = $0004
p_l        = $0005
p_h        = $0006
val_l      = $0007
val_h      = $0008
token      = $0009 ; Multiple bytes

hash_tab_l = $3000
hash_tab_h = $3100
heap       = $3200

; Hash collisions AA/GW/YZ AB/GT/YY AG/GQ/MZ

* = $2000

; Contains each byte $00-$FF exactly once in random order
scramble_tab
  DATA $01 $70 $DE $CD $50 $E6 $D2 $27 $7E $DB $15 $F0 $AF $F1 $A6 $CA
  DATA $31 $03 $C4 $B5 $B3 $A2 $9C $19 $AB $2C $DA $46 $E8 $0F $59 $68
  DATA $09 $69 $9B $FA $3C $E1 $41 $5E $8A $1B $93 $6D $6E $22 $71 $44
  DATA $D4 $FC $24 $E3 $08 $6C $2B $EA $85 $B1 $E4 $FF $37 $F3 $5D $18
  DATA $25 $4E $8F $0C $9E $F9 $3D $58 $76 $81 $0A $0B $D5 $53 $2A $91
  DATA $66 $B0 $95 $98 $AE $77 $60 $26 $80 $55 $ED $5A $14 $78 $FE $F8
  DATA $7B $2D $34 $8E $13 $87 $89 $4B $2E $2F $BF $3B $65 $29 $47 $49
  DATA $D1 $F6 $BD $3F $32 $CE $1F $20 $30 $36 $39 $0E $5F $04 $C0 $A8
  DATA $A5 $BA $43 $F5 $F2 $4C $06 $C3 $D9 $DF $B9 $1D $B7 $E7 $4A $4D
  DATA $73 $3A $C9 $C1 $DC $92 $A3 $7A $96 $BB $EC $61 $11 $E9 $6A $1A
  DATA $42 $75 $51 $A1 $97 $C8 $17 $1C $00 $5C $72 $94 $16 $7C $D3 $84
  DATA $5B $EF $9A $45 $FD $9F $F7 $EB $9D $8D $A4 $C2 $6F $C7 $D0 $64
  DATA $38 $83 $D7 $BC $B6 $74 $CC $07 $AC $7F $33 $99 $3E $EE $28 $8C
  DATA $A7 $57 $62 $1E $86 $4F $40 $D8 $B2 $CF $A9 $E2 $AA $CB $D6 $A0
  DATA $10 $E5 $02 $35 $21 $79 $B8 $C6 $23 $0D $E0 $56 $8B $F4 $52 $12
  DATA $7D $05 $67 $54 $63 $90 $B4 $DD $AD $C5 $6B $82 $FB $BE $48 $88


display_hex_char
  CMP# $0A
  BCS ~display_hex_char_low
  ; Carry alrady clear
  ADC# "0"
  JMP write_b          ; Tail call
display_hex_char_low
  ; C already set
  SBC# $0A ; Subtract 10
  CLC
  ADC# "A"
  JMP write_b ; Tail call


display_hex
  PHA
  LSRA
  LSRA
  LSRA
  LSRA
  JSR display_hex_char
  PLA
  AND# $0F
  JMP display_hex_char ; Tail call


display_carry
  BCS ~dc_carry_set
  ; Carry clear
  LDA# "0"
  JMP write_b
dc_carry_set
  LDA# "1"
  JMP write_b


copy_token
  LDY# $FF
ct_loop
  INY
  LDAZ(),Y <tabp_l
  STA,Y token
  BNE ~ct_loop
  RTS


init_heap
  LDA# <heap
  STAZ <memp_l
  LDA# >heap
  STAZ <memp_h

  RTS


advance_heap
  TYA
  LDY# $00
  CLC
  ADCZ <memp_l
  STAZ <memp_l
  TYA
  ADCZ <memp_h
  STAZ <memp_h
  RTS


init_hash_tab
  LDX# $00
  LDA# $00
iht_loop
  STA,X hash_tab_l
  STA,X hash_tab_h
  INX
  BNE ~iht_loop
  

; On exit Z = 1 if entry is empty
hash_entry_empty
  LDAZ <hash
  TAY
  LDA,Y hash_tab_l
  BNE ~hee_done
  LDA,Y hash_tab_h
hee_done
  RTS


; Load from hash table to tab_l;tab_h
load_hash_entry
  LDAZ <hash
  TAY
  LDA,Y hash_tab_l
  STAZ <tabp_l
  LDA,Y hash_tab_h
  STAZ <tabp_h
  RTS


; Store current memory pointer in hash table
store_hash_entry
  LDAZ <hash
  TAY
  LDAZ <memp_l
  STA,Y hash_tab_l
  LDAZ <memp_h
  STA,Y hash_tab_h
  RTS


; Store current memory pointer in table
store_table_entry
  LDAZ <memp_l
  STAZ(),Y <tabp_l
  INY
  LDAZ <memp_h
  STAZ(),Y <tabp_h
  INY
  RTS


; On entry token contains the token to find
; Raises error if not found
; On exit val_l;val_h contains value
find_in_hash
  JSR calculate_hash
  JSR hash_entry_empty
  BEQ ~fih_notfound
fih_entry_exists
  JSR load_hash_entry
  JSR find_token
  BCS ~fih_notfound
  ; Found
  LDAZ(),Y <tabp_l
  STAZ <val_l
  INY
  LDAZ(),Y <tabp_l
  STAZ <val_h
  RTS
fih_notfound
  BRK $02 "Token not found" $00


; On entry tabp_l;tabp_h point to head of list of entries
;          token contains the token to find
; On exit C clear if found; set if not found
;         tabp_l;tabp_hi,Y points to value if found
;         or to 'next' pointer if not found
find_token
ft_tokenloop
  ; Store the current pointer
  LDAZ <tabp_l
  STAZ <p_l
  LDAZ <tabp_h
  STAZ <p_h
  ; Advance past 'next' pointer
  CLC
  LDA# $02
  ADCZ <tabp_l
  STAZ <tabp_l
  LDA# $00
  ADCZ <tabp_h
  STAZ <tabp_h
  ; Check for matching token
  LDY# $FF
ft_charloop
  INY
  LDAZ(),Y <tabp_l
  CMP,Y token
  BNE ~ft_notmatch
  CMP# $00
  BNE ~ft_charloop
  ; Match
  INY                  ; point tab,Y to value
  CLC
  RTS
ft_notmatch            ; Not a match - move to next
  ; Check if 'next' pointer is 0
  LDY# $00
  LDAZ(),Y <p_l
  BNE ~ft_notmatch1 ; not zero
  INY
  LDAZ(),Y <p_l
  BEQ ~ft_atend
  ; Not at end
  STAZ <tabp_h
  LDA# $00
  STAZ <tabp_l
  JMP ft_tokenloop
ft_notmatch1
  STAZ <tabp_l
  INY
  LDAZ(),Y <p_l
  STAZ <tabp_h
  JMP ft_tokenloop
ft_atend
  ; point tabp,Y to the zero 'next' pointer
  LDAZ <p_l
  STAZ <tabp_l
  LDAZ <p_h
  STAZ <tabp_h
  LDY# $00
  SEC ; Carry set indicates not found
  RTS


store_token
  LDY# $00
  ; Store null pointer (pointer to next)
  LDA# $00
  STAZ(),Y <memp_l
  INY
  STAZ(),Y <memp_l
  INY
  JSR advance_heap
  ; Store token name
  LDY# $FF         ; Alternative: DEY
st_loop
  INY
  LDA,Y token
  STAZ(),Y <memp_l
  BNE ~st_loop
  INY
  ; Store value
  LDAZ <val_l
  STAZ(),Y <memp_l
  INY
  LDAZ <val_h
  STAZ(),Y <memp_l
  INY
  JMP advance_heap ; Tail call


calculate_hash
  LDA# $00
  STAZ <hash
  LDX# $00
ch_loop
  LDAZ,X <token
  BEQ ~ch_done
  EORZ <hash
  TAY
  LDA,Y scramble_tab
  STAZ <hash
  INX
  JMP ch_loop
ch_done
  RTS


; On entry token contains token
;          val_l;val_h contains value
hash_add
  JSR calculate_hash
  JSR hash_entry_empty
  BEQ ~ha_entry_empty
  ; Find in list
  JSR load_hash_entry
  JSR find_token
  BCS ~ha_new
  BRK $01 "Token already exists" $00
ha_new
  JSR store_table_entry
  JMP store_token ; Tail call
ha_entry_empty
  JSR store_hash_entry
ha_store
  JMP store_token ; Tail call


show
  LDY# $00
show_loop
  LDA,Y token
  BEQ ~show_loop_done
  JSR write_b
  INY
  JMP show_loop
show_loop_done
  LDA# " "
  JSR write_b
  LDAZ <val_h
  JSR display_hex
  LDAZ <val_l
  JSR display_hex
  LDA# "\n"
  JSR write_b
  RTS


start
  JSR init_heap
  JSR init_hash_tab

  LDY# $00
test_loop
  LDX# $00
  LDA,Y test_data
  BEQ ~test_loop_done
test_char_loop
  STA,X token
  BEQ ~test_char_loop_done
  INY
  INX
  LDA,Y test_data
  JMP test_char_loop
test_char_loop_done
  INY  
  LDA,Y test_data
  STAZ <val_l
  INY
  LDA,Y test_data
  STAZ <val_h
  INY
  TYA
  PHA

  JSR hash_add

  PLA
  TAY
  JMP test_loop
test_loop_done

  LDA# <key
  STAZ <tabp_l
  LDA# >key
  STAZ <tabp_h
  JSR copy_token

  JSR find_in_hash

  JSR show

  BRK $00


key
  DATA "AB" $00


test_data
  DATA "AA" $00 $0102
  DATA "AB" $00 $0304
  DATA "GW" $00 $0506
  DATA "YZ" $00 $0708
  DATA $00


  DATA start
