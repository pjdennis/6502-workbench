; Requires:
;   HT_KEY       - key buffer address (common.asm alias to TOKEN in asm.asm)
;   HT_V16       - value buffer address (common.asm alias to HEX16 in asm.asm)
;   MEMP16       - heap pointer (common.asm)
;   advance_heap - advance the heap (common.asm)
;   LABEL_SCOPE16    - current scope for local label resolution (hash_table.asm)


  .zeropage

HASH:           .byte       ; 1 byte hash value
CACHED_HASH:    .byte       ; Pre-ASL hash of current global (for local labels)
HTP16:          .word       ; 2 byte pointer to hash table
TABP16:         .word       ; 2 byte table pointer
HTTP16:         .word       ; 2 byte temporary pointer
LABEL_SCOPE16:  .word       ; Current scope for local label resolution
LABEL_TYPE:     .byte       ; Flag: non-zero if storing local label

  .code


; Contains each byte $00-$7F exactly once in random order
scramble_table:
  .byte $01, $20, $33, $1B, $1C, $16, $29, $1F, $3A, $75, $62, $42, $68, $79, $00, $52
  .byte $32, $0B, $22, $77, $72, $71, $10, $59, $06, $4D, $17, $37, $40, $0C, $66, $21
  .byte $1E, $43, $3E, $30, $13, $07, $7E, $44, $6C, $58, $15, $1A, $5A, $24, $0F, $7A
  .byte $7B, $39, $4B, $53, $70, $73, $19, $69, $55, $7D, $4C, $2C, $7C, $47, $23, $61
  .byte $56, $48, $74, $2F, $76, $26, $2E, $2B, $6B, $57, $12, $4F, $25, $64, $0A, $27
  .byte $50, $65, $5D, $31, $2A, $46, $6F, $5F, $67, $54, $18, $49, $05, $11, $03, $6E
  .byte $02, $0E, $34, $5E, $63, $08, $6D, $14, $6A, $0D, $3B, $4E, $3D, $60, $41, $38
  .byte $45, $7F, $3F, $3C, $5C, $2D, $35, $51, $04, $28, $09, $4A, $78, $1D, $36, $5B


; Initialize a hash table
; On entry HTP16 point to the hash table
; On exit hash entries are initialized to 0 (empty table)
;         X is preserved
;         A, Y are not preserved
init_hash_table:
  LDY #$00
  TYA                  ; A <- 0
.loop:
  STA (HTP16),Y
  INY
  BNE .loop
  RTS


; Commit the pre-ASL hash to CACHED_HASH
; Call this when updating CURR_GLOBAL for non-assignment global labels
; On exit A is not preserved
;         X, Y are preserved
commit_cached_hash:
  LDA HASH
  LSR
  STA CACHED_HASH
  RTS

; Calculate hash for local labels
; Continues from CACHED_HASH, hashes HT_KEY (which contains "bar" without dot)
; On exit HASH contains the calculated hash value (post-ASL)
;         X is preserved
;         A, Y are not preserved
calculate_hash_local:
  LDA CACHED_HASH
  STA HASH
  JMP hash_loop ; Tail call


; Calculate hash for global labels or instructions (does NOT use CACHED_HASH)
; On entry HT_KEY contains the token to calculate hash from
; On exit HASH contains the calculated hash value (post-ASL)
;         X is preserved
;         A, Y are not preserved
calculate_hash:
  LDA #$00
  STA HASH
  ; fall through to common code


; Shared hash loop - X = start index, HASH = initial value
; On exit: HASH = pre-ASL result, X at null terminator
; Private by convention (used only by calculate_hash and calculate_hash_local)
hash_loop:
  TXA
  PHA
  LDX #$00
.loop:
  LDA HT_KEY,X
  BEQ .done
  AND #$7F
  EOR HASH
  TAY
  LDA scramble_table,Y
  STA HASH
  INX
  BNE .loop
.done:
  ASL HASH
  PLA
  TAX
  RTS


; On entry HT_KEY contains the key to find
;          LABEL_TYPE: if non-zero, uses cached hash from global
; On exit C = 0 if found or 1 if not found
; On exit TABP16 points to the key if found
;         HT_V16 contains the value if found
;         X is preserved
;         A, Y are not preserverd
find_in_hash:
  LDA LABEL_TYPE
  BEQ .use_global_hash
  JSR calculate_hash_local
  JMP .lookup_value
.use_global_hash:
  JSR calculate_hash
.lookup_value:
  JSR find_in_hash_common
  BCS .done ; Not found
  LDA (TABP16),Y
  STA HT_V16
  INY
  LDA (TABP16),Y
  STA HT_V16 + 1
.done:
  RTS


; Find in hash table for instructions (does not modify CACHED_HASH)
; On entry HT_KEY contains the key to find
; On exit C = 0 if found or 1 if not found
; On exit TABP16 points to the found key
;         TABP16 + Y points to the associated value
;         X is preserved
;         A, is not preserverd
find_in_hash_instruction:
  JSR calculate_hash
  ; Fall through to common code


find_in_hash_common:
  JSR hash_entry_empty
  BEQ .not_found
  ; Entry exists
  JSR load_hash_entry
  JMP find_token          ; Tail call
.not_found:
  SEC
  RTS


; On entry HASH contains the hash value
; On exit Z set if entry is empty, clear otherwise
;         X is preserved
;         A, Y are not preserved
hash_entry_empty:
  LDA HASH
  TAY
  LDA (HTP16),Y
  BNE .done
  INY
  LDA (HTP16),Y
.done:
  RTS


; Load from hash table to TABP16
; On entry HASH contains the hash value
; On exit TABP16 contains pointer corresponding to the hash value
;         X is preserved
;         A, Y are not preserved
load_hash_entry:
  LDA HASH
  TAY
  LDA (HTP16),Y
  STA TABP16
  INY
  LDA (HTP16),Y
  STA TABP16 + 1
  RTS


; Store current memory pointer in hash table
; On entry HASH contains the hash code to store under
;          MEMP16 contains the pointer to store in the hash table
; On exit X is preserved
;         A, Y are not preserved
store_hash_entry:
  LDA HASH
  TAY
  LDA MEMP16
  STA (HTP16),Y
  INY
  LDA MEMP16 + 1
  STA (HTP16),Y
  RTS


; Store current memory pointer in table
; On entry TABP16 + Y points to location to store pointer
;          MEMP16 contains the pointer to store
; On exit TABP16 + Y points to the location following the stored pointer
;         X is preserved
;         A is not preserved
store_table_entry:
  LDA MEMP16
  STA (TABP16),Y
  INY
  LDA MEMP16 + 1
  STA (TABP16),Y
  INY
  RTS


; On entry HT_KEY contains the token to compare with
;          TABP16 points to the value to compare with
;          LABEL_SCOPE16: current scope (for local label verification)
; On exit Z set if equal, unset otherwise
;         Y points to terminating 0 if equal
;         X is preserved
;         A is not preserved
; Handles both normal strings and escape format:
;   <type> <scope_lo> <scope_hi> "local" $00
; For escape format, verifies scope pointer matches before comparing
compare_token:
  ; Quick check: is stored token in escape format?
  ; Escape format starts with type byte ($01=LOCAL, $02=MACRO)
  ; Valid label names start with printable chars >= $20
  LDY #$00
  LDA (TABP16),Y
  CMP #$20
  BCC .handle_escape    ; First byte < $20 means escape format

  ; === Non-escape entry (global label) ===
  ; If we're looking for LOCAL/MACRO type, this global can't match
  LDA LABEL_TYPE
  BNE .escape_nomatch       ; Looking for scoped label, but entry is global
  ; Global lookup - simple string comparison
  DEY                       ; Y = $FF
.simple_loop:
  INY
  LDA (TABP16),Y
  CMP HT_KEY,Y
  BNE .simple_done
  CMP #$00
  BNE .simple_loop
.simple_done:
  RTS

.handle_escape:
  ; === Escape format (<type> <scope_lo> <scope_hi> "bar" $00) ===
  ; First verify type byte matches current LABEL_TYPE
  ; (prevents LOCAL-type entries matching MACRO-type lookups and vice versa)
  ; A already contains the type byte from detection check
  CMP LABEL_TYPE
  BNE .escape_nomatch    ; Type mismatch - no match
  ; Verify scope pointer matches LABEL_SCOPE16
  INY
  LDA (TABP16),Y
  CMP LABEL_SCOPE16
  BNE .escape_nomatch
  INY
  LDA (TABP16),Y
  CMP LABEL_SCOPE16 + 1
  BNE .escape_nomatch
  ; Scope matches - compare local part (Y=2, need Y=3 to skip header)
  ; Use X for HT_KEY index, save/restore since X is file handle
  TXA
  PHA
  LDX #$00
  INY                       ; Y = 3 (past $01 <lo> <hi>)
.escape_loop:
  LDA (TABP16),Y
  CMP HT_KEY,X
  BNE .escape_nomatch_restore
  CMP #$00
  BEQ .escape_match
  INX
  INY
  BNE .escape_loop
.escape_match:
  PLA
  TAX
  LDA #$00                  ; Z=1 (match)
  RTS
.escape_nomatch_restore:
  PLA
  TAX
.escape_nomatch:
  LDA #$01                  ; Z=0 (no match)
  RTS


; On entry TABP16 points to head of list of entries
;          HT_KEY contains the token to find
; On exit C clear if found; set if not found
;         TABP16 points to the key if found
;         TABP16 + Y points to value if found or to 'next' pointer if not found
;         X is preserved
;         A, Y are not preserved
find_token:
.token_loop:
  ; Store the current pointer
  CP16 TABP16, HTTP16
  ; Advance past 'next' pointer
  CLC
  LDA #$02
  ADCA16 TABP16, TABP16
  ; Check for matching token
  JSR compare_token
  BNE .token_is_non_match
  ; Match
  INY                  ; point tab,Y to value
  CLC
  RTS
.token_is_non_match:    ; Not a match - move to next
  ; Load 'next' pointer and check if null
  LDY #$00
  LDA (HTTP16),Y
  STA TABP16
  INY
  LDA (HTTP16),Y
  STA TABP16 + 1
  ORA TABP16
  BEQ .at_end
  JMP .token_loop
.at_end:
  ; point tabp,Y to the zero 'next' pointer
  CP16 HTTP16, TABP16
  LDY #$00
  SEC ; Carry set indicates not found
  RTS


; Stores null next pointer and key on heap
; and advances heap pointer
; On entry HT_KEY contains key to store
;          LABEL_TYPE: if non-zero, stores escape format
;            (HT_KEY contains "bar" without dot for local labels)
;          LABEL_SCOPE16: current scope (for local labels)
; On exit MEMP16 points to where value should be stored
;         Y = 0
;         X is preserved
;         A is not preserved
store_token:
  LDY #$00
  ; Store null pointer (pointer to next)
  LDA #$00
  STA (MEMP16),Y
  INY
  STA (MEMP16),Y
  INY
  JSR advance_heap
  ; Save the pointer to the key
  CP16 MEMP16, TABP16
  ; Check if this is a local label
  LDA LABEL_TYPE
  BEQ .copy_token       ; If global, skip escape header
  ; Store escape format: <type> <scope_lo> <scope_hi> <local_part>
  ; HT_KEY contains "bar" without dot - no scanning needed
  APPEND_HEAP LABEL_TYPE ; Escape byte (type)
  APPEND_HEAP LABEL_SCOPE16
  APPEND_HEAP LABEL_SCOPE16 + 1
  JSR advance_heap      ; Advance past escape header (3 bytes)
  ; Fall through to copy HT_KEY
.copy_token:
  ; Copy token string to heap
  LDY #$FF
.loop:
  INY
  LDA HT_KEY,Y
  STA (MEMP16),Y
  BNE .loop
  INY
  JMP advance_heap      ; Tail call

; Find macro definition in LHASHTAB
; On entry HT_KEY contains the macro name to find
;          HTP16 must point to LHASHTAB (caller must select_label_hash_table)
; On exit C = 0 if found, C = 1 if not found
;         If found: TABP16 + Y points to the associated value
;         X is preserved
;         A, Y are not preserved
find_macro_in_hash:
  LDA #LABEL_TYPE_MACRO_DEF
  STA LABEL_TYPE
  LDA #$00
  STA_LH16 LABEL_SCOPE16
  JSR calculate_hash       ; Global hash (not calculate_hash_local)
  JMP find_in_hash_common  ; Tail call


; Add macro definition to LHASHTAB
; On entry HT_KEY contains the macro name to add
;          HTP16 must point to LHASHTAB (caller must select_label_hash_table)
; On exit C = 0 if added, MEMP16 points to where value should be stored
;         C = 1 if exists, TABP16 + Y points to existing value
;         A, X, Y are not preserved
add_macro_to_hash:
  LDA #LABEL_TYPE_MACRO_DEF
  STA LABEL_TYPE
  LDA #$00
  STA_LH16 LABEL_SCOPE16
  JSR calculate_hash       ; Global hash (not calculate_hash_local)
  JMP hash_add_common      ; Tail call

; Add HT_KEY to hash table
; On entry HT_KEY contains key
;          LABEL_TYPE: if non-zero, uses cached hash from global
; On exit C = 0 if added or 1 if already exists
;         If C = 0 (added), MEMP16 points to where value should be stored
;         Caller must store value and call advance_heap
;         If C = 1 (exists), TABP16 points to the key and TABP16 + Y points to the value
;         A, X, Y are not preserved
hash_add:
  LDA LABEL_TYPE
  BEQ .use_global_hash
  JSR calculate_hash_local
  JMP .hash_done
.use_global_hash:
  JSR calculate_hash
.hash_done:
; Fall through to common code


hash_add_common:
  JSR hash_entry_empty
  BEQ .entry_empty
  JSR load_hash_entry
  JSR find_token
  BCS .new
  SEC
  RTS
.new:
  JSR store_table_entry
  JMP .store
.entry_empty:
  JSR store_hash_entry
.store:
  JSR store_token
  CLC
  RTS
