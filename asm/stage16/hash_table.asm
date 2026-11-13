; Requires:
;   HT_KEY       - the address of the key used for hash table operations
;   HT_VL;HT_VH  - zero page locations containing value in hash table
;   MEMPL;MEMPH  - addres of heap to store table entries
;   advance_heap - function to advance the heap
;   CURR_GLOBAL_HEAP_L;CURR_GLOBAL_HEAP_H - heap address of current global label (for local labels)


  .zeropage

HASH      .data $00     ; 1 byte hash value
CACHED_HASH .data $00   ; Pre-ASL hash of current global (for local labels)
HTPL      .data $00     ; 2 byte pointer to hash table
HTPH      .data $00     ; "
TABPL     .data $00     ; 2 byte table pointer
TABPH     .data $00     ; "
HTTPL     .data $00     ; 2 byte temporary pointer
HTTPH     .data $00     ; "
IS_LOCAL_LABEL .data $00 ; Flag: non-zero if storing local label

  .code


; Contains each byte $00-$7F exactly once in random order
scramble_table
  .data $01 $20 $33 $1B $1C $16 $29 $1F $3A $75 $62 $42 $68 $79 $00 $52
  .data $32 $0B $22 $77 $72 $71 $10 $59 $06 $4D $17 $37 $40 $0C $66 $21
  .data $1E $43 $3E $30 $13 $07 $7E $44 $6C $58 $15 $1A $5A $24 $0F $7A
  .data $7B $39 $4B $53 $70 $73 $19 $69 $55 $7D $4C $2C $7C $47 $23 $61
  .data $56 $48 $74 $2F $76 $26 $2E $2B $6B $57 $12 $4F $25 $64 $0A $27
  .data $50 $65 $5D $31 $2A $46 $6F $5F $67 $54 $18 $49 $05 $11 $03 $6E
  .data $02 $0E $34 $5E $63 $08 $6D $14 $6A $0D $3B $4E $3D $60 $41 $38
  .data $45 $7F $3F $3C $5C $2D $35 $51 $04 $28 $09 $4A $78 $1D $36 $5B


; Initialize a hash table
; On entry HTPL;HTPH point to the hash table
; On exit hash entries are initialized to 0 (empty table)
;         X is preserved
;         A, Y are not preserved
init_hash_table
  LDY #$00
  TYA                  ; A <- 0
.loop
  STA (HTPL),Y
  INY
  BNE .loop
  RTS


; Calculate hash for global labels
; On entry HT_KEY contains the token to calculate hash from
; On exit HASH contains the calculated hash value (post-ASL)
;         HASH_PRE_ASL contains pre-ASL value (NOT committed to CACHED_HASH)
;         X is preserved
;         A, Y are not preserved
; Note: Caller must call commit_cached_hash to update CACHED_HASH if needed
calculate_hash
  LDA #$00
  STA HASH
  JMP hash_loop ; Tail call


; Commit the pre-ASL hash to CACHED_HASH
; Call this when updating CURR_GLOBAL for non-assignment global labels
; On exit A is not preserved
;         X, Y are preserved
commit_cached_hash
  LDA HASH
  LSR
  STA CACHED_HASH
  RTS

; Calculate hash for local labels
; Continues from CACHED_HASH, hashes HT_KEY (which will contain just ".bar")
; On exit HASH contains the calculated hash value (post-ASL)
;         X is preserved
;         A, Y are not preserved
calculate_hash_local
  LDA CACHED_HASH
  STA HASH
  JMP hash_loop ; Tail call


; Calculate hash for instructions (does NOT modify CACHED_HASH)
; On entry HT_KEY contains the token to calculate hash from
; On exit HASH contains the calculated hash value (post-ASL)
;         CACHED_HASH is NOT modified
;         X is preserved
;         A, Y are not preserved
calculate_hash_instruction
  LDA #$00
  STA HASH
  ; fall through to common code


; Shared hash loop - X = start index, HASH = initial value
; On exit: HASH = pre-ASL result, X at null terminator
; Private by convention (used only by calculate_hash and calculate_hash_local)
hash_loop
  TXA
  PHA
  LDX #$00
.loop
  LDA HT_KEY,X
  BEQ .done
  AND #$7F
  EOR HASH
  TAY
  LDA scramble_table,Y
  STA HASH
  INX
  BNE .loop
.done
  ASL HASH
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
  LDA IS_LOCAL_LABEL
  BEQ .use_global_hash
  JSR calculate_hash_local
  JMP .lookup_value
.use_global_hash
  JSR calculate_hash
.lookup_value
  JSR find_in_hash_common
  BCS .done ; Not found
  LDA (TABPL),Y
  STA HT_VL
  INY
  LDA (TABPL),Y
  STA HT_VH
.done
  RTS


; Find in hash table for instructions (does not modify CACHED_HASH)
; On entry HT_KEY contains the key to find
; On exit C = 0 if found or 1 if not found
; On exit TABPL:TABPH points to the found key
;         TABPL:TABPH+Y points to the associated value
;         X is preserved
;         A, is not preserverd
find_in_hash_instruction
  JSR calculate_hash_instruction
  ; Fall through to common code


find_in_hash_common
  JSR hash_entry_empty
  BEQ .not_found
  ; Entry exists
  JSR load_hash_entry
  JSR find_token
  RTS
.not_found
  SEC
  RTS


; On entry HASH contains the hash value
; On exit Z set if entry is empty, clear otherwise
;         X is preserved
;         A, Y are not preserved
hash_entry_empty
  LDA HASH
  TAY
  LDA (HTPL),Y
  BNE .done
  INY
  LDA (HTPL),Y
.done
  RTS


; Load from hash table to TABPL;TABPH
; On entry HASH contains the hash value
; On exit TABPL;TABPH countains pointer corresponding to the hash value
;         X is preserved
;         A, Y are not preserved
load_hash_entry
  LDA HASH
  TAY
  LDA (HTPL),Y
  STA TABPL
  INY
  LDA (HTPL),Y
  STA TABPH
  RTS


; Store current memory pointer in hash table
; On entry HASH contains the hash code to store under
;          MEMPL;MEMPH contains the pointer to store in the hash table
; On exit X is preserved
;         A, Y are not preserved
store_hash_entry
  LDA HASH
  TAY
  LDA MEMPL
  STA (HTPL),Y
  INY
  LDA MEMPH
  STA (HTPL),Y
  RTS


; Store current memory pointer in table
; On entry TABPL;TABPH,Y points to location to store pointer
;          MEMPL;NENPL contains the pointer to store
; On exit TABPL;TABPH,Y points to the location following the stored pointer
;         X is preserved
;         A is not preserved
store_table_entry
  LDA MEMPL
  STA (TABPL),Y
  INY
  LDA MEMPH
  STA (TABPL),Y
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
  LDY #$00
  LDA (TABPL),Y
  CMP #$01
  BEQ .handle_escape

  ; === Fast path (no escape) - simple string comparison ===
  DEY                       ; Y = $FF
.simple_loop
  INY
  LDA (TABPL),Y
  CMP HT_KEY,Y
  BNE .simple_done
  CMP #$00
  BNE .simple_loop
.simple_done
  RTS

.handle_escape
  ; === Escape format ($01 <ptr_lo> <ptr_hi> ".bar" $00) ===
  ; Verify scope pointer matches CURR_GLOBAL_HEAP
  INY
  LDA (TABPL),Y
  CMP CURR_GLOBAL_HEAP_L
  BNE .escape_nomatch
  INY
  LDA (TABPL),Y
  CMP CURR_GLOBAL_HEAP_H
  BNE .escape_nomatch
  ; Scope matches - compare local part (Y=2, need Y=3 to skip header)
  ; Use X for HT_KEY index, save/restore since X is file handle
  TXA
  PHA
  LDX #$00
  INY                       ; Y = 3 (past $01 <lo> <hi>)
.escape_loop
  LDA (TABPL),Y
  CMP HT_KEY,X
  BNE .escape_nomatch_restore
  CMP #$00
  BEQ .escape_match
  INX
  INY
  BNE .escape_loop
.escape_match
  PLA
  TAX
  LDA #$00                  ; Z=1 (match)
  RTS
.escape_nomatch_restore
  PLA
  TAX
.escape_nomatch
  LDA #$01                  ; Z=0 (no match)
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
.token_loop
  ; Store the current pointer
  LDA TABPL
  STA HTTPL
  LDA TABPH
  STA HTTPH
  ; Advance past 'next' pointer
  CLC
  LDA #$02
  ADC TABPL
  STA TABPL
  LDA #$00
  ADC TABPH
  STA TABPH
  ; Check for matching token
  JSR compare_token
  BNE .token_is_non_match
  ; Match
  INY                  ; point tab,Y to value
  CLC
  RTS
.token_is_non_match    ; Not a match - move to next
  ; Check if 'next' pointer is 0
  LDY #$00
  LDA (HTTPL),Y
  BNE .not_at_end
  INY
  LDA (HTTPL),Y
  BEQ .at_end
.not_at_end
  LDY #$00
  LDA (HTTPL),Y
  STA TABPL
  INY
  LDA (HTTPL),Y
  STA TABPH
  JMP .token_loop
.at_end
  ; point tabp,Y to the zero 'next' pointer
  LDA HTTPL
  STA TABPL
  LDA HTTPH
  STA TABPH
  LDY #$00
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
  LDY #$00
  ; Store null pointer (pointer to next)
  LDA #$00
  STA (MEMPL),Y
  INY
  STA (MEMPL),Y
  INY
  JSR advance_heap
  ; Save the pointer to the key
  LDA MEMPL
  STA TABPL
  LDA MEMPH
  STA TABPH
  ; Check if this is a local label
  LDA IS_LOCAL_LABEL
  BEQ .copy_token       ; If global, skip escape header
  ; Store $01 escape format: $01 <addr_lo> <addr_hi> <local_part>
  ; HT_KEY already contains just ".bar" - no scanning needed
  LDA #$01              ; Escape byte
  STA (MEMPL),Y
  INY
  LDA CURR_GLOBAL_HEAP_L
  STA (MEMPL),Y
  INY
  LDA CURR_GLOBAL_HEAP_H
  STA (MEMPL),Y
  INY
  JSR advance_heap      ; Advance past escape header (3 bytes)
  ; Fall through to copy HT_KEY
.copy_token
  ; Copy token string to heap
  LDY #$FF
.loop
  INY
  LDA HT_KEY,Y
  STA (MEMPL),Y
  BNE .loop
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
  LDA IS_LOCAL_LABEL
  BEQ .use_global_hash
  JSR calculate_hash_local
  JMP .hash_done
.use_global_hash
  JSR calculate_hash
.hash_done
  JSR hash_entry_empty
  BEQ .entry_empty
  JSR load_hash_entry
  JSR find_token
  BCS .new
  SEC
  RTS
.new
  JSR store_table_entry
  JMP .store
.entry_empty
  JSR store_hash_entry
.store
  JSR store_token
  CLC
  RTS
