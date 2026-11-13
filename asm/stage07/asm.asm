; inst.asm prepended to provide instruction hash table


; Provided by environment:
;   read_b:  Returns next character in A
;            C set when at end
;            Automatically restarts input after reaching end
;
;   write_b: Writes A to output
read_b    = $F006
write_b   = $F009

LHASHTABL = $4000      ; Label hash table (low and high)
LHASHTABH = $4080      ; "
HEAP      = $4100      ; Data heap

TEMP      = $0000      ; 1 byte
TABPL     = $0001      ; 2 byte table pointer
TABPH     = $0002      ; "
PCL       = $0003      ; 2 byte program counter
PCH       = $0004      ; "
HEX1      = $0005      ; 1 byte
HEX2      = $0006      ; 1 byte
PASS      = $0007      ; 1 byte $00 = pass 1 $FF = pass 2
MEMPL     = $0008      ; 2 byte heap pointer
MEMPH     = $0009      ; "
PL        = $000A      ; 2 byte pointer
PH        = $000B      ; "
HASH      = $000C      ; 1 byte hash value
HTLPL     = $000D      ; 2 byte pointer to low byte hash table
HTLPH     = $000E      ; "
HTHPL     = $000F      ; 2 byte pointer to high byte hash table
HTHPH     = $0010      ; "
TOKEN     = $0011      ; multiple bytes

; Environment should surface error codes and messages on BRK
err_labelnotfound
  BRK $01 "Label not found" $00

err_duplicatelabel
  BRK $02 "Duplicate label" $00

err_opcodenotfound
  BRK $03 "Opcode not found" $00

err_expectedhex
  BRK $04 "Expected hex value" $00

err_branchoutofrange
  BRK $05 "Branch out of range" $00


init_heap
  LDA# <HEAP
  STAZ <MEMPL
  LDA# >HEAP
  STAZ <MEMPH
  RTS


advance_heap
  TYA
  LDY# $00
  CLC
  ADCZ <MEMPL
  STAZ <MEMPL
  TYA
  ADCZ <MEMPH
  STAZ <MEMPH
  RTS


select_label_hash_table
  LDA# <LHASHTABL
  STAZ <HTLPL
  LDA# >LHASHTABL
  STAZ <HTLPH
  LDA# <LHASHTABH
  STAZ <HTHPL
  LDA# >LHASHTABH
  STAZ <HTHPH
  RTS


select_instruction_hash_table
  LDA# <IHASHTABL
  STAZ <HTLPL
  LDA# >IHASHTABL
  STAZ <HTLPH
  LDA# <IHASHTABH
  STAZ <HTHPL
  LDA# >IHASHTABH
  STAZ <HTHPH
  RTS


init_hash_table
  LDY# $00
  TYA                  ; A <- 0
iht_loop
  STAZ(),Y <HTLPL
  STAZ(),Y <HTHPL
  INY
  BNE ~iht_loop
  RTS
  

calculate_hash
  LDA# $00
  STAZ <HASH
  LDX# $00
ch_loop
  LDAZ,X <TOKEN
  BEQ ~ch_done
  EORZ <HASH
  TAY
  LDA,Y scramble_table
  STAZ <HASH
  INX
  JMP ch_loop
ch_done
  RTS


; On exit Z = 1 if entry is empty
hash_entry_empty
  LDAZ <HASH
  TAY
  LDAZ(),Y <HTLPL
  BNE ~hee_done
  LDAZ(),Y <HTHPL
hee_done
  RTS


; Load from hash table to TABPL;TABPH
load_hash_entry
  LDAZ <HASH
  TAY
  LDAZ(),Y <HTLPL
  STAZ <TABPL
  LDAZ(),Y <HTHPL
  STAZ <TABPH
  RTS


; Store current memory pointer in hash table
store_hash_entry
  LDAZ <HASH
  TAY
  LDAZ <MEMPL
  STAZ(),Y <HTLPL
  LDAZ <MEMPH
  STAZ(),Y <HTHPL
  RTS


; Store current memory pointer in table
store_table_entry
  LDAZ <MEMPL
  STAZ(),Y <TABPL
  INY
  LDAZ <MEMPH
  STAZ(),Y <TABPL
  INY
  RTS


; On entry TABPL;TABPH point to head of list of entries
;          TOKEN contains the token to find
; On exit C clear if found; set if not found
;         TABPL;TABPHi,Y points to value if found
;         or to 'next' pointer if not found
find_token
ft_tokenloop
  ; Store the current pointer
  LDAZ <TABPL
  STAZ <PL
  LDAZ <TABPH
  STAZ <PH
  ; Advance past 'next' pointer
  CLC
  LDA# $02
  ADCZ <TABPL
  STAZ <TABPL
  LDA# $00
  ADCZ <TABPH
  STAZ <TABPH
  ; Check for matching token
  LDY# $FF
ft_charloop
  INY
  LDAZ(),Y <TABPL
  CMP,Y TOKEN
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
  LDAZ(),Y <PL
  BNE ~ft_notmatch1 ; not zero
  INY
  LDAZ(),Y <PL
  BEQ ~ft_atend
  ; Not at end
  STAZ <TABPH
  LDA# $00
  STAZ <TABPL
  JMP ft_tokenloop
ft_notmatch1
  STAZ <TABPL
  INY
  LDAZ(),Y <PL
  STAZ <TABPH
  JMP ft_tokenloop
ft_atend
  ; point tabp,Y to the zero 'next' pointer
  LDAZ <PL
  STAZ <TABPL
  LDAZ <PH
  STAZ <TABPH
  LDY# $00
  SEC ; Carry set indicates not found
  RTS


; On entry token contains the token to find
; On exit C = 0 if found or 1 if not found
; On exit HEX1 and HEX2 contains MSB and LSB of value if found
find_in_hash
  JSR calculate_hash
  JSR hash_entry_empty
  BEQ ~fih_notfound
  ; Entry exists
  JSR load_hash_entry
  JSR find_token
  BCS ~fih_notfound
  ; Found
  LDAZ(),Y <TABPL
  STAZ <HEX2
  INY
  LDAZ(),Y <TABPL
  STAZ <HEX1
  CLC
  RTS
fih_notfound
  SEC
  RTS


; On entry HEX1 and HEX2 contain MSB and LSB of value
;          TOKEN contains name of token
; Stores null next pointer, token and value on heap
; and advances heap pointer 
store_token
  LDY# $00
  ; Store null pointer (pointer to next)
  LDA# $00
  STAZ(),Y <MEMPL
  INY
  STAZ(),Y <MEMPL
  INY
  JSR advance_heap
  ; Store token name
  LDY# $FF         ; Alternative: DEY
st_loop
  INY
  LDA,Y TOKEN
  STAZ(),Y <MEMPL
  BNE ~st_loop
  INY
  ; Store value
  LDAZ <HEX2
  STAZ(),Y <MEMPL
  INY
  LDAZ <HEX1
  STAZ(),Y <MEMPL
  INY
  JMP advance_heap ; Tail call


; On entry TOKEN contains token
;          HEX1 and HEX2 contain MSB and LSB of value
; On exit C = 0 if added or 1 if already exists
hash_add
  JSR calculate_hash
  JSR hash_entry_empty
  BEQ ~ha_entry_empty
  JSR load_hash_entry
  JSR find_token
  BCS ~ha_new
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


; On entry A contains the byte to emit
; On exit A, X, Y are preserved
emit
  BITZ <PASS
  BPL ~emit_incpc      ; Skip writing during pass 1
  JSR write_b
emit_incpc
  INCZ <PCL
  BNE ~emit_done
  INCZ <PCH
emit_done
  RTS


skiprestofline
  CMP# "\n"
  BEQ ~srol_done
  JSR read_b
  JMP skiprestofline
srol_done
  RTS


skipspaces
  CMP# " "
  BNE ~ss_done
  JSR read_b
  JMP skipspaces
ss_done
  RTS


cmpendoftoken
  CMP# " "
  BEQ ~ceof_end
  CMP# "\n"
  BEQ ~ceof_end
  CMP# ";"
ceof_end
  RTS


; Checks for end of line and skips past if at end
; On entry A contains next character
; On exit C set if end of line, clear otherwise
;         A contains next character
checkforend
  CMP# ";"
  BEQ ~cfe_end
  CMP# "\n"
  BEQ ~cfe_end
  ; Not at end
  CLC
  RTS
cfe_end
  JSR skiprestofline
  SEC
  RTS


; On entry A contains first character of token
; Reads token into TOKEN (zero terminated)
; On exit A contains next character after token
;         Y is preserved
;         X is not preserved
readtoken
  LDX# $00
readtokenloop
  STAZ,X <TOKEN
  INX
  JSR read_b
  JSR cmpendoftoken
  BNE ~readtokenloop
  PHA                  ; Save next char
  LDA# $00
  STAZ,X <TOKEN
  PLA                  ; Restore next char
  RTS


; On exit A contains the next character
readandfindexistinglabel
  JSR readtoken
  BITZ <PASS
  BMI ~rafel_pass2
  ; Pass 1
  RTS
rafel_pass2
  PHA                  ; Save next char
  JSR select_label_hash_table
  JSR find_in_hash
  BCC ~rafel_found
  JMP err_labelnotfound
rafel_found
  PLA                  ; Restore next char
  RTS


; On entry, A contains a hex character A-Z|0-9
; On exit A contains the value (0-15)
convhex
  CMP# "A"
  BCC ~ch_numeric      ; < 'A'
  SBC# "A"             ; Carry already set
  CLC
  ADC# $0A             ; ADC# 10
  RTS
ch_numeric
  SEC
  SBC# "0"
  RTS


; On entry A contains first hex character
; Reads second hex character; Uses TEMP
; On exit A contains 2 character value (0-255)
readhex
  JSR convhex
  ASLA
  ASLA
  ASLA
  ASLA
  STAZ <TEMP
  JSR read_b
  JSR convhex
  ORAZ <TEMP
  RTS


; On entry, next character read will be first hex character
; On exit C set if 2 bytes read clear if 1 byte read
;         A contains the next character
grabhex
  JSR read_b           ; Read the 1st hex character
  JSR readhex          ; Read 2nd hex character and convert
  STAZ <HEX1
  JSR read_b           ; Read 3rd hex char or terminator
  JSR cmpendoftoken
  BNE ~gh_second
  CLC                  ; No second byte so return C = 0
  RTS
gh_second
  JSR readhex          ; Read 4th hex char and convert
  STAZ <HEX2
  JSR read_b           ; Read next char
  SEC                  ; Second byte so return C = 1
  RTS


; Read 2 to 4 hex characters and emit 1 or 2 bytes
; When 2 bytes, emit LSB then MSB
; Uses HEX1, HEX2
; On exit A contains next character
emithex
  JSR grabhex          ; Returns C = 1 if 2 bytes read
  PHA                  ; Save next char
  BCC ~eh_one
  LDAZ <HEX2
  JSR emit
eh_one
  LDAZ <HEX1
  JSR emit
  PLA                  ; Restore next char
  RTS


; On entry A contains the next character
; On exit C set if value read; clear otherwise
readvalue
  JSR skipspaces
  CMP# "="
  BEQ ~rv_value
  CLC
  RTS
rv_value
  JSR read_b           ; Read the character after the "="
  JSR skipspaces
  CMP# "$"
  BEQ ~rv_hexvalue
  JMP err_expectedhex
rv_hexvalue
  JSR grabhex
  BCS ~rv_ok
  PHA
  LDAZ <HEX1
  STAZ <HEX2
  LDA# $00
  STAZ <HEX1
  PLA
rv_ok
  SEC
  RTS


; capturelabel
capturelabel
  JSR readtoken
  PHA                  ; Save next char
  LDAZ <TOKEN
  CMP# "*"
  BNE ~cl_normallabel
  ; Set PC
  PLA                  ; Restore next char
  JSR readvalue
  JSR skiprestofline
  ; No need to retain next char as caller
  ; goes straight to next line
  LDAZ <HEX2
  STAZ <PCL
  LDAZ <HEX1
  STAZ <PCH
  RTS
cl_normallabel
  BITZ <PASS
  BPL ~cl_pass1
  ; Pass 2 - don't capture
  PLA                  ; Restore next char
  JMP skiprestofline   ; Tail call
cl_pass1
  PLA                  ; Restore next char
  JSR readvalue
  PHA                  ; Save next char
  BCS ~cl_hextotable
  ; Store program counter
  LDAZ <PCL
  STAZ <HEX2
  LDAZ <PCH
  STAZ <HEX1
cl_hextotable
  JSR select_label_hash_table
  JSR hash_add
  PLA                  ; Restore next char
  BCC ~cl_added
  JMP err_duplicatelabel
cl_added
  JSR skiprestofline
  ; No need to retain next char as caller
  ; goes straight to next line
  RTS


; Emit the opcode
; On exit A contains the next character
emitopcode
  JSR readtoken
  PHA                  ; Save next char
  JSR select_instruction_hash_table
  JSR find_in_hash
  BCC ~eo_found
  PLA                  ; Restore next char
  JMP err_opcodenotfound
eo_found
  LDAZ <HEX2
  AND# $01
  BNE ~eo_done         ; Not opcode (DATA command)
  ; Opcode
  LDAZ <HEX1
  JSR emit
eo_done
  PLA                  ; Restore next char
  RTS


; Read and emit quoted ASCII
emitquoted
  JSR read_b
  CMP# "\""
  BNE ~eq_notdone
  JSR read_b           ; Done; read next char
  RTS
eq_notdone
  CMP# "\\"
  BNE ~eq_notescaped
  JSR read_b
  CMP# "n"
  BNE ~eq_notescaped
  LDA# "\n"            ; Escaped "n" is linefeed
eq_notescaped
  JSR emit
  JMP emitquoted


; On exit A contains the next character
emitlabel
  JSR readandfindexistinglabel
  PHA                  ; Save next char
  ; Emit low byte then high byte from table
  LDAZ <HEX2
  JSR emit
  LDAZ <HEX1
  JSR emit
  PLA                  ; Restore next char
  RTS


; On exit A contains the next character
emitlabellsb
  JSR readandfindexistinglabel
  PHA                  ; Save next char
  ; Emit low byte
  LDAZ <HEX2
  JSR emit
  PLA                  ; Restore next char
  RTS


; On exit A contains the next character
emitlabelbyte
  JMP emitlabellsb


; On exit A contains the next character
emitlabelmsb
  JSR readandfindexistinglabel
  PHA                  ; Save next char
  ; Emit high byte
  LDAZ <HEX1
  JSR emit
  PLA                  ; Restore next character
  RTS


; On exit A contains the next character
emitlabelrel
  BITZ <PASS
  BMI ~elr_pass2
  ; Pass 1
  JSR readtoken
  JSR emit
  RTS
elr_pass2
  JSR readandfindexistinglabel
  PHA                  ; Save next char

  ; Calculate target - PC - 1
  CLC ; for the - 1
  LDAZ <HEX2
  SBCZ <PCL
  STAZ <HEX2
  LDAZ <HEX1
  SBCZ <PCH

  CMP# $00
  BEQ ~elr_forward
  CMP# $FF
  BEQ ~elr_backward
  JMP err_branchoutofrange

elr_forward
  LDAZ <HEX2
  AND# $80
  BEQ ~elr_ok
  JMP err_branchoutofrange

elr_backward
  LDAZ <HEX2
  AND# $80
  BNE ~elr_ok
  JMP err_branchoutofrange

elr_ok
  LDAZ <HEX2
  JSR emit
  PLA                  ; Restore next char
  RTS


; Main assembler
assemble
  LDA# $00
  STAZ <PCL
  STAZ <PCH
lnloop
  JSR read_b
  BCC ~lnloop1
  RTS                  ; At end of input
lnloop1
  JSR checkforend
  BCS ~lnloop
  CMP# " "
  BEQ ~lnloop2
  JSR capturelabel
  JMP lnloop
lnloop2
  JSR skipspaces
  JSR checkforend
  BCS ~lnloop
  ; Read mnemonic and emit opcode
  JSR emitopcode
tokloop
  JSR skipspaces
  JSR checkforend
  BCS ~lnloop          ; End of line
  CMP# "\""            ; Quoted string
  BNE ~tokloop1
  JSR emitquoted
  JMP tokloop
tokloop1
  CMP# "$"             ; 1 or 2 byte hex
  BNE ~tokloop2
  JSR emithex
  JMP tokloop
tokloop2
  CMP# "<"             ; LSB of variable
  BNE ~tokloop3
  JSR read_b
  JSR emitlabellsb
  JMP tokloop
tokloop3
  CMP# ">"             ; MSB of variable
  BNE ~tokloop4
  JSR read_b
  JSR emitlabelmsb
  JMP tokloop
tokloop4
  CMP# "~"             ; Relative address
  BNE ~tokloop5
  JSR read_b
  JSR emitlabelrel
  JMP tokloop
tokloop5
  PHA
  LDAZ <HEX2
  AND# $02
  BEQ ~tokloop6
  PLA
  JSR emitlabelrel
  JMP tokloop
tokloop6
  LDAZ <HEX2
  AND# $04
  BEQ ~tokloop7
  PLA
  JSR emitlabelbyte
  JMP tokloop
tokloop7
  PLA
  JSR emitlabel        ; 2 byte variable
  JMP tokloop


; Entry point
start
  JSR init_heap
  JSR select_label_hash_table
  JSR init_hash_table
  LDA# $00
  STAZ <PASS           ; Bit 7 = 0 (pass 1)
  JSR assemble
  LDA# $FF
  STAZ <PASS           ; Bit 7 = 1 (pass 2)
  JSR assemble
  BRK $00              ; Success


  DATA start ; Emulation environment jumps to address in last 2 bytes
