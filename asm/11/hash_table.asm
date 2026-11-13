; Requires:
;   HT_KEY       - the address of the key used for hash table operations
;   HT_VL;HT_VH  - zero page locations containing value in hash table
;   MEMPL;MEMPH  - addres of heap to store table entries
;   advance_heap - function to advance the heap
;   CURR_GLOBAL_HEAP_L;CURR_GLOBAL_HEAP_H - heap address of current global label (for local labels)


  .zeropage

HASH      DATA $00     ; 1 byte hash value
CACHED_HASH DATA $00   ; Pre-ASL hash of current global (for local labels)
HTPL      DATA $00     ; 2 byte pointer to hash table
HTPH      DATA $00     ; "
TABPL     DATA $00     ; 2 byte table pointer
TABPH     DATA $00     ; "
HTTPL     DATA $00     ; 2 byte temporary pointer
HTTPH     DATA $00     ; "
IS_LOCAL_LABEL DATA $00 ; Flag: non-zero if storing local label

  .code


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


; Initialize a hash table
; On entry HTPL;HTPH point to the hash table
; On exit hash entries are initialized to 0 (empty table)
;         X is preserved
;         A, Y are not preserved
init_hash_table
  LDY# $00
  TYA                  ; A <- 0
init_hash_table_loop
  STAZ(),Y HTPL
  INY
  BNE init_hash_table_loop
  RTS


; Calculate hash for global labels
; On entry HT_KEY contains the token to calculate hash from
; On exit HASH contains the calculated hash value (post-ASL)
;         HASH_PRE_ASL contains pre-ASL value (NOT committed to CACHED_HASH)
;         X is preserved
;         A, Y are not preserved
; Note: Caller must call commit_cached_hash to update CACHED_HASH if needed
calculate_hash
  LDA# $00
  STAZ HASH
  JMP hash_loop ; Tail call


; Commit the pre-ASL hash to CACHED_HASH
; Call this when updating CURR_GLOBAL for non-assignment global labels
; On exit A is not preserved
;         X, Y are preserved
commit_cached_hash
  LDAZ HASH
  LSRA
  STAZ CACHED_HASH
  RTS

; Calculate hash for local labels
; Continues from CACHED_HASH, hashes HT_KEY (which will contain just ".bar")
; On exit HASH contains the calculated hash value (post-ASL)
;         X is preserved
;         A, Y are not preserved
calculate_hash_local
  LDAZ CACHED_HASH
  STAZ HASH
  JMP hash_loop ; Tail call


; Calculate hash for instructions (does NOT modify CACHED_HASH)
; On entry HT_KEY contains the token to calculate hash from
; On exit HASH contains the calculated hash value (post-ASL)
;         CACHED_HASH is NOT modified
;         X is preserved
;         A, Y are not preserved
calculate_hash_instruction
  LDA# $00
  STAZ HASH
  ; fall through to common code


; Shared hash loop - X = start index, HASH = initial value
; On exit: HASH = pre-ASL result, X at null terminator
; Private by convention (used only by calculate_hash and calculate_hash_local)
hash_loop
  TXA
  PHA
  LDX# $00
hash_loop_loop
  LDA,X HT_KEY
  BEQ hash_loop_done
  AND# $7F
  EORZ HASH
  TAY
  LDA,Y scramble_table
  STAZ HASH
  INX
  BNE hash_loop_loop
hash_loop_done
  ASLZ HASH
  PLA
  TAX
  RTS


; On entry HT_KEY contains the key to find
;          IS_LOCAL_LABEL: if non-zero, uses cached hash from global
; On exit C = 0 if found or 1 if not found
; On exit TABPL;TABPH points to the key if found
;         HT_VL;HT_VH contains the value if found
;         X is preserved
;         A, Y are not preserverd
find_in_hash
  LDAZ IS_LOCAL_LABEL
  BEQ find_in_hash_use_global_hash
  JSR calculate_hash_local
  JMP find_in_hash_common
find_in_hash_use_global_hash
  JSR calculate_hash
  JMP find_in_hash_common


; Find in hash table for instructions (does not modify CACHED_HASH)
; On entry HT_KEY contains the key to find
; On exit C = 0 if found or 1 if not found
; On exit HT_VL;HT_VH contains the value if found
;         X is preserved
;         A, Y are not preserverd
find_in_hash_instruction
  JSR calculate_hash_instruction
  ; Fall through to common code


find_in_hash_common
  JSR hash_entry_empty
  BEQ find_in_hash_common_not_found
  ; Entry exists
  JSR load_hash_entry
  JSR find_token
  BCS find_in_hash_common_not_found
  ; Found
  LDAZ(),Y TABPL
  STAZ HT_VL
  INY
  LDAZ(),Y TABPL
  STAZ HT_VH
  CLC
  RTS
find_in_hash_common_not_found
  SEC
  RTS


; On entry HASH contains the hash value
; On exit Z set if entry is empty, clear otherwise
;         X is preserved
;         A, Y are not preserved
hash_entry_empty
  LDAZ HASH
  TAY
  LDAZ(),Y HTPL
  BNE hash_entry_empty_done
  INY
  LDAZ(),Y HTPL
hash_entry_empty_done
  RTS


; Load from hash table to TABPL;TABPH
; On entry HASH contains the hash value
; On exit TABPL;TABPH countains pointer corresponding to the hash value
;         X is preserved
;         A, Y are not preserved
load_hash_entry
  LDAZ HASH
  TAY
  LDAZ(),Y HTPL
  STAZ TABPL
  INY
  LDAZ(),Y HTPL
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
  STAZ(),Y HTPL
  INY
  LDAZ MEMPH
  STAZ(),Y HTPL
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


; On entry HT_KEY contains the token to compare with
;          TABPL;TABPH points to the value to compare with
;          CURR_GLOBAL_HEAP_L/H: current scope (for local label verification)
; On exit Z set if equal, unset otherwise
;         Y points to terminating 0 if equal
;         X is preserved
;         A is not preserved
; Handles both normal strings and $01 escape format:
;   $01 <addr_lo> <addr_hi> ".local" $00
; For escape format, verifies scope pointer matches before comparing
compare_token
  ; Quick check: is stored token in escape format?
  LDY# $00
  LDAZ(),Y TABPL
  CMP# $01
  BEQ compare_token_handle_escape

  ; === Fast path (no escape) - simple string comparison ===
  DEY                       ; Y = $FF
compare_token_simple_loop
  INY
  LDAZ(),Y TABPL
  CMP,Y HT_KEY
  BNE compare_token_simple_done
  CMP# $00
  BNE compare_token_simple_loop
compare_token_simple_done
  RTS

compare_token_handle_escape
  ; === Escape format ($01 <ptr_lo> <ptr_hi> ".bar" $00) ===
  ; Verify scope pointer matches CURR_GLOBAL_HEAP
  INY
  LDAZ(),Y TABPL
  CMPZ CURR_GLOBAL_HEAP_L
  BNE compare_token_escape_nomatch
  INY
  LDAZ(),Y TABPL
  CMPZ CURR_GLOBAL_HEAP_H
  BNE compare_token_escape_nomatch
  ; Scope matches - compare local part (Y=2, need Y=3 to skip header)
  ; Use X for HT_KEY index, save/restore since X is file handle
  TXA
  PHA
  LDX# $00
  INY                       ; Y = 3 (past $01 <lo> <hi>)
compare_token_escape_loop
  LDA,X HT_KEY
  STAZ TEMP
  LDAZ(),Y TABPL
  CMPZ TEMP
  BNE compare_token_escape_nomatch_restore
  CMP# $00
  BEQ compare_token_escape_match
  INX
  INY
  BNE compare_token_escape_loop
compare_token_escape_match
  PLA
  TAX
  LDA# $00                  ; Z=1 (match)
  RTS
compare_token_escape_nomatch_restore
  PLA
  TAX
compare_token_escape_nomatch
  LDA# $01                  ; Z=0 (no match)
  RTS


; On entry TABPL;TABPH point to head of list of entries
;          HT_KEY contains the token to find
; On exit C clear if found; set if not found
;         TABPL;TABPH points to the key if found
;         TABPL;TABPH,Y points to value if found
;         or to 'next' pointer if not found
;         X is preserved
;         A, Y are not preserved
find_token
find_token_token_loop
  ; Store the current pointer
  LDAZ TABPL
  STAZ HTTPL
  LDAZ TABPH
  STAZ HTTPH
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
  BNE find_token_token_is_non_match
  ; Match
  INY                  ; point tab,Y to value
  CLC
  RTS
find_token_token_is_non_match    ; Not a match - move to next
  ; Check if 'next' pointer is 0
  LDY# $00
  LDAZ(),Y HTTPL
  BNE find_token_not_at_end
  INY
  LDAZ(),Y HTTPL
  BEQ find_token_at_end
find_token_not_at_end
  LDY# $00
  LDAZ(),Y HTTPL
  STAZ TABPL
  INY
  LDAZ(),Y HTTPL
  STAZ TABPH
  JMP find_token_token_loop
find_token_at_end
  ; point tabp,Y to the zero 'next' pointer
  LDAZ HTTPL
  STAZ TABPL
  LDAZ HTTPH
  STAZ TABPH
  LDY# $00
  SEC ; Carry set indicates not found
  RTS


; Stores null next pointer and key on heap
; and advances heap pointer
; On entry HT_KEY contains key to store
;          IS_LOCAL_LABEL: if non-zero, stores $01 escape format
;            (HT_KEY should already contain just ".bar" for local labels)
;          CURR_GLOBAL_HEAP_L/H: pointer to global label (for local labels)
; On exit MEMPL;MEMPH points to where value should be stored
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
  ; Save the pointer to the key
  LDAZ MEMPL
  STAZ TABPL
  LDAZ MEMPH
  STAZ TABPH
  ; Check if this is a local label
  LDAZ IS_LOCAL_LABEL
  BEQ store_token_copy_token       ; If global, skip escape header
  ; Store $01 escape format: $01 <addr_lo> <addr_hi> <local_part>
  ; HT_KEY already contains just ".bar" - no scanning needed
  LDA# $01              ; Escape byte
  STAZ(),Y MEMPL
  INY
  LDAZ CURR_GLOBAL_HEAP_L
  STAZ(),Y MEMPL
  INY
  LDAZ CURR_GLOBAL_HEAP_H
  STAZ(),Y MEMPL
  INY
  JSR advance_heap      ; Advance past escape header (3 bytes)
  ; Fall through to copy HT_KEY
store_token_copy_token
  ; Copy token string to heap
  LDY# $FF
store_token_loop
  INY
  LDA,Y HT_KEY
  STAZ(),Y MEMPL
  BNE store_token_loop
  INY
  JMP advance_heap      ; Tail call


; Add HT_KEY to hash table
; On entry HT_KEY contains key
;          IS_LOCAL_LABEL: if non-zero, uses cached hash from global
; On exit C = 0 if added or 1 if already exists
;         If C = 0, MEMPL;MEMPH points to where value should be stored
;         Caller must store value and call advance_heap
;         A, X, Y are not preserved
hash_add
  LDAZ IS_LOCAL_LABEL
  BEQ hash_add_use_global_hash
  JSR calculate_hash_local
  JMP hash_add_hash_done
hash_add_use_global_hash
  JSR calculate_hash
hash_add_hash_done
  JSR hash_entry_empty
  BEQ hash_add_entry_empty
  JSR load_hash_entry
  JSR find_token
  BCS hash_add_new
  SEC
  RTS
hash_add_new
  JSR store_table_entry
  JMP hash_add_store
hash_add_entry_empty
  JSR store_hash_entry
hash_add_store
  JSR store_token
  CLC
  RTS
