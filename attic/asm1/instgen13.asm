; Addresses
TOKEN      = $1E00      ; Buffer for the current token being read
IHASHTAB   = $1F00      ; Instruction hash table
*          = $2000      ; Code generates here


  .zeropage

TEMP      DATA $00     ; 1 byte temporary value
HEX1      DATA $00     ; 1 byte
HEX2      DATA $00     ; 1 byte
MEMPL     DATA $00     ; 2 byte heap pointer
MEMPH     DATA $00     ; "
PL        DATA $00     ; 2 byte pointer
PH        DATA $00     ; "
P2L       DATA $00     ; 2 byte pointer
P2H       DATA $00     ; "


  .code

; Include files
  .include environment.asm
  .include common13.asm


; Instruction table
MNTAB
;      Mnemonic           Opcode
  DATA "ADC#"     $00 $04 $69
  DATA "ADCZ"     $00 $04 $65
  DATA "AND#"     $00 $04 $29
  DATA "ASLA"     $00 $00 $0A
  DATA "ASLZ"     $00 $04 $06
  DATA "BCC"      $00 $02 $90
  DATA "BCS"      $00 $02 $B0
  DATA "BEQ"      $00 $02 $F0
  DATA "BITZ"     $00 $04 $24
  DATA "BMI"      $00 $02 $30
  DATA "BNE"      $00 $02 $D0
  DATA "BPL"      $00 $02 $10
  DATA "BRK"      $00 $00 $00
  DATA "CLC"      $00 $00 $18
  DATA "CMPZ"     $00 $04 $C5
  DATA "CMP#"     $00 $04 $C9
  DATA "CMP,Y"    $00 $00 $D9
  DATA "CPXZ"     $00 $04 $E4
  DATA "CPYZ"     $00 $04 $C4
  DATA "CPY#"     $00 $04 $C0
  DATA "DECZ"     $00 $04 $C6
  DATA "DEX"      $00 $00 $CA
  DATA "DEY"      $00 $00 $88
  DATA "EORZ"     $00 $04 $45
  DATA "INCZ"     $00 $04 $E6
  DATA "INX"      $00 $00 $E8
  DATA "INY"      $00 $00 $C8
  DATA "JMP"      $00 $00 $4C
  DATA "JSR"      $00 $00 $20
  DATA "LDA"      $00 $00 $AD
  DATA "LDX"      $00 $00 $AE
  DATA "LDY"      $00 $00 $AC
  DATA "LDA#"     $00 $04 $A9
  DATA "LDAZ(),Y" $00 $04 $B1
  DATA "LDA,X"    $00 $00 $BD
  DATA "LDA,Y"    $00 $00 $B9
  DATA "LDAZ"     $00 $04 $A5
  DATA "LDAZ,X"   $00 $04 $B5
  DATA "LDXZ"     $00 $04 $A6
  DATA "LDYZ"     $00 $04 $A4
  DATA "LDX#"     $00 $04 $A2
  DATA "LDY#"     $00 $04 $A0
  DATA "LSRA"     $00 $00 $4A
  DATA "ORAZ"     $00 $04 $05
  DATA "PHA"      $00 $00 $48
  DATA "PLA"      $00 $00 $68
  DATA "ROLZ"     $00 $04 $26
  DATA "RTS"      $00 $00 $60
  DATA "SBC#"     $00 $04 $E9
  DATA "SBCZ"     $00 $04 $E5
  DATA "SEC"      $00 $00 $38
  DATA "STA"      $00 $00 $8D
  DATA "STAZ(),Y" $00 $04 $91
  DATA "STA,X"    $00 $00 $9D
  DATA "STA,Y"    $00 $00 $99
  DATA "STAZ"     $00 $04 $85
  DATA "STAZ,X"   $00 $04 $95
  DATA "STXZ"     $00 $04 $86
  DATA "STYZ"     $00 $04 $84
  DATA "TAX"      $00 $00 $AA
  DATA "TAY"      $00 $00 $A8
  DATA "TSX"      $00 $00 $BA
  DATA "TXA"      $00 $00 $8A
  DATA "TYA"      $00 $00 $98
  DATA "DATA"     $00 $01 $00 ; Directive
  DATA $00


populate_instruction_hash_table
  LDA# <MNTAB
  STAZ P2L
  LDA# >MNTAB
  STAZ P2H
piht_entry_loop
  LDY# $00
  LDAZ(),Y P2L
  BEQ piht_done
piht_token_loop
  STA,Y TOKEN
  BEQ piht_token_loop_done
  INY
  LDAZ(),Y P2L
  JMP piht_token_loop
piht_token_loop_done
  INY
  LDAZ(),Y P2L
  STAZ HEX2
  INY
  LDAZ(),Y P2L
  STAZ HEX1
  INY
  ; Advance
  TYA
  CLC
  ADCZ P2L
  STAZ P2L
  LDA# $00
  ADCZ P2H
  STAZ P2H
  ; Store entry
  JSR hash_add
  JMP piht_entry_loop
piht_done
  RTS


display_hex_char
  CMP# $0A
  BCS display_hex_char_low
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


display_byte
  PHA
  LDA# "$"
  JSR write_b
  PLA
  JMP display_hex


display_newline
  LDA# "\n"
  JMP write_b


display_data_prefix
  LDA# " "
  JSR write_b
  JSR write_b
  LDA# <msg_data
  STAZ PL
  LDA# >msg_data
  STAZ PH
  JMP display_text


; On entry PL;PH points to the text
; On exit Y points to the terminating 0
display_text
  LDY# $00
dtext_loop
  LDAZ(),Y PL
  BEQ dtext_done
  JSR write_b
  INY
  JMP dtext_loop
dtext_done
  RTS


display_table
  LDA# $00
  STAZ HASH
dt_loop
  ; Display line start
  JSR display_data_prefix
  ; Display line
  LDA# $00
  STAZ TEMP
dt_lineloop
  LDA# " "
  JSR write_b
  JSR hash_entry_empty
  BNE dt_not_empty
  ; empty
  LDA# "$"
  JSR write_b
  LDA# $00
  JSR display_hex
  LDA# $00
  JSR display_hex
  JMP dt_next
dt_not_empty
  ; Display instruction label prefix
  LDA# <msg_instprefix
  STAZ PL
  LDA# >msg_instprefix
  STAZ PH
  JSR display_text
  ; Display hash entry
  JSR load_hash_entry
  CLC
  LDAZ TABPL
  ADC# $02
  STAZ PL
  LDAZ TABPH
  ADC# $00
  STAZ PH
  JSR display_text
dt_next
  LDAZ HASH
  CLC
  ADC# $02
  STAZ HASH
  LDAZ TEMP
  CLC
  ADC# $01
  STAZ TEMP
  CMP# $08
  BEQ dt_next1
  JMP dt_lineloop
dt_next1
  JSR display_newline
  LDAZ HASH
  BEQ dt_done 
  JMP dt_loop
dt_done
  RTS


write_label
  LDA# " "
  JSR write_b
  LDA# "\""
  JSR write_b
  CLC
  LDAZ TABPL
  ADC# $02
  STAZ PL
  LDAZ TABPH
  ADC# $00
  STAZ PH
  JSR display_text
  LDA# "\""
  JSR write_b
  LDA# " "
  JSR write_b
  LDA# $00
  JSR display_byte
  LDA# " "
  JSR write_b
  INY
  LDAZ(),Y PL
  JSR display_byte
  LDA# " "
  JSR write_b
  INY
  LDAZ(),Y PL
  JSR display_byte
  JSR display_newline
  RTS 


display_data
  LDA# $00
  STAZ HASH
dd_loop
  JSR hash_entry_empty
  BNE dd_not_empty
  JMP dd_next
dd_not_empty
  ; Load pointer to hash entry
  JSR load_hash_entry
dd_entry_loop
  ; Display instruction label prefix
  LDA# <msg_instprefix
  STAZ PL
  LDA# >msg_instprefix
  STAZ PH
  JSR display_text
  CLC
  LDAZ TABPL
  ADC# $02
  STAZ PL
  LDAZ TABPH
  ADC# $00
  STAZ PH
  JSR display_text
  JSR display_newline
  JSR display_data_prefix
  LDA# " "
  JSR write_b
  ; Display next pointer
  LDY# $00
  LDAZ(),Y TABPL
  BNE dd_not_zero
  INY
  LDAZ(),Y TABPL
  BNE dd_not_zero
  ; Zero
  LDA# "$"
  JSR write_b
  LDA# "0"
  JSR write_b
  JSR write_b
  JSR write_b
  JSR write_b
  JSR write_label
  JMP dd_next
dd_not_zero
  LDA# <msg_instprefix
  STAZ PL
  LDA# >msg_instprefix
  STAZ PH
  JSR display_text
  CLC
  LDY# $00
  LDAZ(),Y TABPL
  ADC# $02
  STAZ PL
  INY
  LDAZ(),Y TABPL
  ADC# $00
  STAZ PH
  JSR display_text
  JSR write_label
  LDY# $00
  LDAZ(),Y TABPL
  STAZ PL
  INY
  LDAZ(),Y TABPL
  STAZ PH
  LDAZ PL
  STAZ TABPL
  LDAZ PH
  STAZ TABPH
  JMP dd_entry_loop
dd_next
  LDAZ HASH
  CLC
  ADC# $02
  STAZ HASH
  BEQ dd_done
  JMP dd_loop
dd_done
  RTS


; Entry point
start
; Initialization
  JSR init_heap
  JSR select_instruction_hash_table
  JSR init_hash_table
  JSR populate_instruction_hash_table

; Show the instructions hash table
  LDA# <msg_hash_table_comment
  STAZ PL
  LDA# >msg_hash_table_comment
  STAZ PH
  JSR display_text
  JSR display_newline
  LDA# <msg_IHASHTAB
  STAZ PL
  LDA# >msg_IHASHTAB
  STAZ PH
  JSR display_text
  JSR display_newline
  JSR display_table
  JSR display_newline

; Show the instructions heap data
  LDA# <msg_heap_comment
  STAZ PL
  LDA# >msg_heap_comment
  STAZ PH
  JSR display_text
  JSR display_newline
  JSR display_data

  BRK $00              ; Success


msg_data
  DATA "DATA" $00

msg_instprefix
  DATA "i_" $00

msg_IHASHTAB
  DATA "IHASHTAB" $00

msg_hash_table_comment
  DATA "; Instructions hash table (pointers)" $00

msg_heap_comment
  DATA "; Instructions heap data" $00


HEAP                  ; Heap goes after the program code


  DATA start ; Emulation environment jumps to address in last 2 bytes
