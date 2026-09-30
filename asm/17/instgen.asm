; Instruction table generator for new conventional syntax
; Written in new syntax (assembled by asm18)
;
; New table format: each instruction has mode:opcode pairs
;   [mnemonic string] $00 [mode1 opcode1] [mode2 opcode2] ... MODE_END
;
; Mode encoding:
;   MODE_NONE  = $00  ; Implied (no operand)
;   MODE_IMM   = $01  ; Immediate
;   MODE_ZP    = $02  ; Zero page
;   MODE_ZPX   = $03  ; Zero page, X
;   MODE_ZPY   = $04  ; Zero page, Y
;   MODE_ABS   = $05  ; Absolute
;   MODE_ABSX  = $06  ; Absolute, X
;   MODE_ABSY  = $07  ; Absolute, Y
;   MODE_INDX  = $08  ; Indirect, X - ($zp,X)
;   MODE_INDY  = $09  ; Indirect, Y - ($zp),Y
;   MODE_REL   = $0A  ; Relative (branches)
;   MODE_IND   = $0B  ; Indirect - JMP ($xxxx)
;   MODE_DIRECTIVE = $0D  ; Directive handler entry
;   MODE_END   = $0F  ; Terminator (end of mode list)
;
; Requires:
;   init_heap, advance_heap, select_instruction_hash_table (common.asm)
;   init_hash_table, hash_add, hash_entry_empty, load_hash_entry (hash_table.asm)
;   write_b (environment.asm), display_hex/display_text helpers (local below)
;   LABEL_TYPE, LABEL_TYPE_GLOBAL, MODE_DIRECTIVE, MODE_END constants (common.asm)

; Addresses
TOKEN       = $1E00     ; Buffer for the current token being read
IHASHTAB    = $1F00     ; Instruction hash table
SOURCE_STACK  = $F000     ; Source stack (needed by advance_heap check)
*           = $2000     ; Code generates here


  .zeropage

TEMP:      .byte         ; 1 byte temporary value
HEX16:     .word         ; 2 bytes
P16:       .word         ; 2 byte pointer
P2_16:     .word         ; 2 byte pointer
SS_P16:    .word         ; Source stack pointer - needed by advance_heap check
SS_PEND_P16: .word       ; Pending top of source stack. instgen has no
                         ; reservation flow, so this is identical to
                         ; SS_P16 at all times -- declared here only so
                         ; advance_heap's CHECK_FOR_OUT_OF_MEMORY (now
                         ; against SS_PEND_P16) links cleanly.

  .code


; Include files
  .include environment.asm
  .include macros.asm
  .include common.asm
  .include instruction_tables.asm


; Copy name from (P2_16) to TOKEN buffer and add to hash table
; On entry: A contains first byte of name (already checked non-zero by caller)
;           P2_16 points to start of name in table
; On exit: P2_16 advanced past name + null terminator
;          MEMP16 points to where value data should be stored
;          TOKEN contains the name (for callers that need it)
;          A, X, Y are not preserved
hash_add_from_table:
  LDY #0
.copy_loop:
  STA TOKEN,Y
  CMP #$00              ; STA doesn't set flags; explicitly test for null
  BEQ .copy_end
  INY
  LDA (P2_16),Y
  JMP .copy_loop
.copy_end:
  TYA
  SEC                         ; +1 for null
  ADCA16 P2_16, P2_16
  JSR hash_add
  RTS


; Populate instruction hash table from MNTAB
;
; MNTAB format (each entry):
;   "MNEMONIC" $00 [mode1 opcode1] [mode2 opcode2] ... MODE_END
;   - Null-terminated mnemonic string
;   - Pairs of (addressing_mode, opcode) bytes
;   - MODE_END terminator marks end of mode list
;   - $00 as first byte marks end of entire table
;
; Hash table entry format (on heap after hash_add):
;   [next_ptr_lo] [next_ptr_hi] [mnemonic $00] [mode opcode]... MODE_END
;   - hash_add stores next_ptr and mnemonic
;   - This routine appends the mode:opcode pairs and MODE_END terminator
;
populate_instruction_hash_table:
  SET16 MNTAB, P2_16 ; P2_16 points to start of instruction table

.entry_loop:
  ; Check for end of table ($00 as first byte of entry)
  LDY #0
  LDA (P2_16),Y
  BEQ .done

  ; --- Phases 1+2: Copy mnemonic to TOKEN and add to hash table ---
  JSR hash_add_from_table

  ; --- Phase 3: Copy mode:opcode pairs to heap ---
  ; Problem: both (P2_16),Y and (MEMP16),Y need Y for indirect indexed mode
  ; Solution: solved above by advancing P2_16 such that its required Y offset matches that required by the heap (i.e. starting at 0)
  LDY #0                    ; Set initial source offset to mode data and to heap

.copy_modes:
  LDA (P2_16),Y               ; Load mode byte from source
  CMP #MODE_END
  BEQ .copy_done
  STA (MEMP16),Y
  INY
  LDA (P2_16),Y               ; Load opcode byte from source
  STA (MEMP16),Y
  INY
  JMP .copy_modes

.copy_done:
  ; Store MODE_END terminator
  APPEND_HEAPI MODE_END

  ; Advance P2_16 to next entry (add Y = total bytes consumed from this entry)
  TYA
  CLC
  ADCA16 P2_16, P2_16 ; P2_16 + Y -> P2_16

  ; Advance the heap
  JSR advance_heap

  JMP .entry_loop

.done:
  RTS


; Populate directive entries in instruction hash table from DIRTAB
;
; DIRTAB format (each entry):
;   "directive" $00
;   - Null-terminated directive name
;   - $00 as first byte marks end of entire table
;
; Hash table entry format (on heap after hash_add):
;   [next_ptr_lo] [next_ptr_hi] [directive $00] MODE_DIRECTIVE "dir_<name>" $00
;   - hash_add stores next_ptr and directive name
;   - This routine appends MODE_DIRECTIVE and constructs handler label "dir_" + name
;
; Register usage:
;   P2_16 = pointer to current entry in DIRTAB (source)
;   MEMP16 = heap pointer (destination), managed by hash_add/advance_heap
;   X, Y = offsets during copy
;
populate_directive_hash_table:
  SET16 DIRTAB, P2_16

.entry_loop:
  ; Check for end of table ($00 as first byte of entry)
  LDY #0
  LDA (P2_16),Y
  BEQ .done

  ; --- Phases 1+2: Copy name to TOKEN and add to hash table ---
  JSR hash_add_from_table

  ; --- Phase 3: Construct MODE_DIRECTIVE + "dir_" + name on heap ---
  ; MEMP16 points to value start, Y = 0 from hash_add
  APPEND_HEAPI MODE_DIRECTIVE
  APPEND_HEAPI 'd'
  APPEND_HEAPI 'i'
  APPEND_HEAPI 'r'
  APPEND_HEAPI '_'
  ; Copy directive name from TOKEN (still valid after hash_add)
  LDX #$00
.copy_name:
  LDA TOKEN,X
  STA (MEMP16),Y
  BEQ .copy_done
  INX
  INY
  JMP .copy_name
.copy_done:
  INY                    ; Count includes null terminator

  ; Advance the heap
  JSR advance_heap

  JMP .entry_loop

.done:
  RTS


display_hex_char:
  CMP #10
  BCS .low
  ; Carry already clear
  ADC #'0'
  JMP write_b          ; Tail call
.low:
  CLC
  ADC #'A' - 10
  JMP write_b ; Tail call


display_hex:
  PHA
  LSR
  LSR
  LSR
  LSR
  JSR display_hex_char
  PLA
  AND #$0F
  JMP display_hex_char ; Tail call


display_byte:
  PHA
  LDA #'$'
  JSR write_b
  PLA
  JMP display_hex


display_newline:
  LDA #'\n'
  JMP write_b


display_word_prefix:
  LDA #' '
  JSR write_b
  JSR write_b
  SET16 msg_word, P16
  JMP display_text

display_byte_prefix:
  LDA #' '
  JSR write_b
  JSR write_b
  SET16 msg_byte, P16
  JMP display_text

display_asciiz_prefix:
  LDA #' '
  JSR write_b
  JSR write_b
  SET16 msg_asciiz, P16
  JMP display_text

display_comma:
  LDA #','
  JSR write_b
  LDA #' '
  JMP write_b


; On entry P16 points to the text
; On exit Y points to the terminating 0
display_text:
  LDY #0
.loop:
  LDA (P16),Y
  BEQ .done
  JSR write_b
  INY
  JMP .loop
.done:
  RTS


display_table:
  LDA #$00
  STA HASH
.loop:
  ; Display line start
  JSR display_word_prefix
  LDA #' '
  JSR write_b
  ; Display first entry
  JSR display_table_entry
  ; Display remaining 7 entries with comma prefix
  LDA #0
  STA TEMP
.lineloop:
  JSR display_comma
  JSR display_table_entry
  LDA TEMP
  CLC
  ADC #1
  STA TEMP
  CMP #7
  BNE .lineloop
  JSR display_newline
  LDA HASH
  BEQ .done
  JMP .loop
.done:
  RTS

; Display a single hash table entry (a .word value)
; Advances HASH by 2
display_table_entry:
  JSR hash_entry_empty
  BNE .not_empty
  ; empty - display 0
  LDA #'0'
  JSR write_b
  JMP .advance
.not_empty:
  ; Display instruction label prefix
  SET16 msg_instprefix, P16
  JSR display_text
  ; Display hash entry name
  JSR load_hash_entry
  CLC
  ADCI16 TABP16, $02, P16
  JSR display_text
.advance:
  LDA HASH
  CLC
  ADC #2
  STA HASH
  RTS


write_mnemonic_and_modes:
  ; Display .asciiz "NAME"
  JSR display_asciiz_prefix
  LDA #' '
  JSR write_b
  LDA #'"'
  JSR write_b
  ; Set P16 to point to name (TABP16 + 2)
  CLC
  ADCI16 TABP16, $02, P16
  ; Display name text
  JSR display_text
  ; Y now points to null terminator in name
  LDA #'"'
  JSR write_b
  JSR display_newline
  ; Check for directive entry (value starts at Y+1)
  INY
  LDA (P16),Y
  CMP #MODE_DIRECTIVE
  BEQ .write_directive
  DEY                  ; Restore Y to null terminator
  ; --- Instruction entry: display mode:opcode pairs ---
  ; Save Y (offset to null terminator) and P16 before display_byte_prefix
  ; display_byte_prefix clobbers P16
  TYA
  PHA
  PUSH16 P16
  ; Now display mode:opcode pairs as .byte line
  JSR display_byte_prefix
  LDA #' '
  JSR write_b
  ; Restore P16 and Y
  POP16 P16
  PLA
  TAY
  ; Y still valid from display_text, pointing at null
  INY                  ; Skip past null terminator to first mode byte
  ; Display first mode byte
  LDA (P16),Y
  JSR display_byte
.mode_loop:
  INY
  LDA (P16),Y
  CMP #MODE_END
  BEQ .mode_done
  ; Display comma and mode byte
  PHA
  JSR display_comma
  PLA
  JSR display_byte
  JMP .mode_loop
.mode_done:
  ; Display final MODE_END
  JSR display_comma
  LDA #MODE_END
  JSR display_byte
  JMP display_newline  ; Tail call
.write_directive:
  ; --- Directive entry: display MODE_DIRECTIVE + handler label ---
  ; Y points to MODE_DIRECTIVE byte, P16 = TABP16 + 2
  ; Save Y and P16 before display_byte_prefix clobbers P16
  TYA
  PHA
  PUSH16 P16
  ; Display "  .byte $0D"
  JSR display_byte_prefix
  LDA #' '
  JSR write_b
  LDA #MODE_DIRECTIVE
  JSR display_byte
  JSR display_newline
  ; Display "  .word "
  JSR display_word_prefix
  LDA #' '
  JSR write_b
  ; Restore P16 and Y
  POP16 P16
  PLA
  TAY
  ; Y points to MODE_DIRECTIVE, advance to handler name
  INY
  ; Display handler name as text
.handler_loop:
  LDA (P16),Y
  BEQ .handler_done
  JSR write_b
  INY
  JMP .handler_loop
.handler_done:
  JMP display_newline  ; Tail call


display_data:
  LDA #$00
  STA HASH
.loop:
  JSR hash_entry_empty
  BNE .not_empty
  JMP .next
.not_empty:
  ; Load pointer to hash entry
  JSR load_hash_entry
.entry_loop:
  ; Display label: .MNEMONIC:
  SET16 msg_instprefix, P16
  JSR display_text
  CLC
  ADCI16 TABP16, $02, P16
  JSR display_text
  LDA #':'
  JSR write_b
  JSR display_newline
  ; Display next pointer as .word
  JSR display_word_prefix
  LDA #' '
  JSR write_b
  LDY #$00
  LDA (TABP16),Y
  BNE .not_zero
  INY
  LDA (TABP16),Y
  BNE .not_zero
  ; Zero - no collision chain
  LDA #'0'
  JSR write_b
  JSR display_newline
  JSR write_mnemonic_and_modes
  JMP .next
.not_zero:
  ; Has collision chain - display pointer to next entry as label
  SET16 msg_instprefix, P16
  JSR display_text
  CLC
  LDY #0
  LDA (TABP16),Y
  ADC #2
  STA P16
  INY
  LDA (TABP16),Y
  ADC #0
  STA P16 + 1
  JSR display_text
  JSR display_newline
  JSR write_mnemonic_and_modes
  LDY #0
  LDA (TABP16),Y
  STA P16
  INY
  LDA (TABP16),Y
  STA P16 + 1
  CP16 P16, TABP16
  JMP .entry_loop
.next:
  LDA HASH
  CLC
  ADC #2
  STA HASH
  BEQ .done
  JMP .loop
.done:
  RTS


; Entry point
start:
; Initialization
  LDA #LABEL_TYPE_GLOBAL
  STA LABEL_TYPE    ; Clear flag before using hash table
  JSR init_heap
  SET16 SOURCE_STACK, SS_P16 ; Initialize so heap overflow check works
  SET16 SOURCE_STACK, SS_PEND_P16
  JSR select_instruction_hash_table
  JSR init_hash_table
  JSR populate_instruction_hash_table
  JSR populate_directive_hash_table

; Show the hash table
  SET16 msg_hash_table_comment, P16
  JSR display_text
  JSR display_newline
  SET16 msg_IHASHTAB, P16
  JSR display_text
  LDA #':'
  JSR write_b
  JSR display_newline
  JSR display_table
  JSR display_newline

; Show the heap data
  SET16 msg_heap_comment, P16
  JSR display_text
  JSR display_newline
  JSR display_data

  BRK
  .byte 0                ; Success


msg_word:
  .asciiz ".word"

msg_byte:
  .asciiz ".byte"

msg_asciiz:
  .asciiz ".asciiz"

msg_instprefix:
  .asciiz "."

msg_IHASHTAB:
  .asciiz "IHASHTAB"

msg_hash_table_comment:
  .asciiz "; Instructions and directives hash table (pointers)"

msg_heap_comment:
  .asciiz "; Instructions and directives heap data"

; Error handler needed by advance_heap's overflow check
err_out_of_memory:
  BRK
  .asciiz 35, "Out of memory"


HEAP:                  ; Heap goes after the program code


  .word start ; Emulation environment jumps to address in last 2 bytes
