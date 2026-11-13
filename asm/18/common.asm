; common.asm - Shared constants, heap utilities, and hash table helpers
;
; Requires:
;   TOKEN, HEX16     - base token/value buffers for HT_KEY/HT_V16 aliases (asm.asm)
;   HEAP, SOURCE_STACK - memory layout symbols for init_heap (asm.asm)
;   SS_P16           - source stack pointer for heap/stack collision checks (source_stack.asm)
;   SMALL_HEAP_FLAG  - debug flag for small-heap mode (asm.asm, optional)
;   err_out_of_memory - error handler for heap/stack collision (errors.asm)
;
; Provides:
;   init_heap, advance_heap, store_hash_value,
;   select_label_hash_table, select_instruction_hash_table
;   HASH/HTP16/HT_V16 helpers via included hash_table.asm

; Addressing mode operand number of bytes
OPERAND_BYTES_0 = 0 << 4
OPERAND_BYTES_1 = 1 << 4
OPERAND_BYTES_2 = 2 << 4

; Addressing mode constants
; Upper nybble: operand bytes
; Lower nybble: mode type (0 to 15)
MODE_NONE  =  0 + OPERAND_BYTES_0 ; Implied (no operand)
MODE_IMM   =  1 + OPERAND_BYTES_1 ; Immediate
MODE_ZP    =  2 + OPERAND_BYTES_1 ; Zero page
MODE_ZPX   =  3 + OPERAND_BYTES_1 ; Zero page, X
MODE_ZPY   =  4 + OPERAND_BYTES_1 ; Zero page, Y
MODE_ABS   =  5 + OPERAND_BYTES_2 ; Absolute
MODE_ABSX  =  6 + OPERAND_BYTES_2 ; Absolute, X
MODE_ABSY  =  7 + OPERAND_BYTES_2 ; Absolute, Y
MODE_INDX  =  8 + OPERAND_BYTES_1 ; Indirect, X - ($zp,X)
MODE_INDY  =  9 + OPERAND_BYTES_1 ; Indirect, Y - ($zp),Y
MODE_REL   = 10 + OPERAND_BYTES_1 ; Relative (branches)
MODE_IND   = 11 + OPERAND_BYTES_2 ; Indirect - JMP ($xxxx)
MODE_DIRECTIVE = 13               ; Directive handler (stored in IHASHTAB)
MODE_END   = 15                   ; Terminates the list of modes

; Label type constants (for LABEL_TYPE variable in hash table operations)
LABEL_TYPE_GLOBAL = 0   ; Global label (no escape format)
LABEL_TYPE_LOCAL  = 1   ; Local label under global scope (heap address)
; (value 2 was LABEL_TYPE_MACRO before Phase 4.7 -- macro parameters
; are now stored as slots in their macro frame's payload, not in the
; hash table, so no LABEL_TYPE value is needed for them)
LABEL_TYPE_MACRO_LOCAL = 3 ; Macro-local label (expansion ID)
LABEL_TYPE_MACRO_DEF  = 4 ; Macro definition (stored in LHASHTAB)

HT_KEY = TOKEN
HT_V16 = HEX16


  .zeropage

MEMP16:          .word       ; 2 byte heap pointer

  .code


  ; Append A to heap and increment Y
  .macro APPEND_HEAPA
  STA (MEMP16),Y
  INY
  .endmacro

  ; Append the value at ptr to the heap and increment Y
  ; Clobbers A
  .macro APPEND_HEAP ptr
  LDA ptr
  APPEND_HEAPA
  .endmacro

  ; Append A to heap and increment Y. Advance heap if 128 entries pending
  .macro APPEND_HEAPA_ADVANCE
  APPEND_HEAPA
  BPL .done
  JSR advance_heap
.done:
  .endmacro

  ; Append val to the heap and increment Y
  .macro APPEND_HEAPI val
  LDA #val
  STA (MEMP16),Y
  INY
  .endmacro


  .include hash_table.asm


; CHECK_FOR_OUT_OF_MEMORY - Verify heap/stack don't collide
; Macro performs the check, to minimize function call overhead
; On entry: fs_ptr = source stack pointer to check against MEMP16
; Raises err_out_of_memory if fs_ptr - MEMP16 < 256
; On exit: A not preserved, X and Y preserved
  .macro CHECK_FOR_OUT_OF_MEMORY fs_ptr
  ; Quick check: if ptr_H - MEMP16_H > 1, we have >= 512 bytes free
  LDA fs_ptr + 1
  SEC
  SBC MEMP16 + 1        ; A = high byte difference
  CMP #$02
  BCS .oom_ok           ; >= 2 means >= 512 bytes, definitely safe
  ; High bytes are close (differ by 0 or 1) - do precise check
  ; Check: ptr - MEMP16 >= 256 (high byte of difference must be non-zero)
  LDA fs_ptr
  SEC
  SBC MEMP16            ; Low byte of difference (result discarded, need borrow)
  LDA fs_ptr + 1
  SBC MEMP16 + 1        ; A = high byte of (ptr - MEMP16)
  BNE .oom_ok           ; Non-zero means >= 256 bytes free
  JMP err_out_of_memory
.oom_ok:
  .endmacro


init_heap:
  .ifdef enable_debug
  LDA SMALL_HEAP_FLAG
  BEQ .normal_heap
  ; Small heap for testing: only ~384 bytes available
  SET16 SOURCE_STACK - $0180, MEMP16
  RTS
.normal_heap:
  .endif
  SET16 HEAP, MEMP16
  RTS


; On entry Y contains the amount to advance
; On exit MEMP16 is incremented by Y
;         Y = 0
;         X is preserved
;         A is not preserved
advance_heap:
  TYA
  LDY #$00
  CLC
  ADC MEMP16
  STA MEMP16
  BCC .done
  INC MEMP16 + 1
.done:
  ; Check for collision with source stack. Use SS_PEND_P16 (the lowest
  ; extent including any in-flight reservation) so the pending region
  ; is structurally protected from heap write-ahead. Outside a
  ; reserve/commit window SS_PEND_P16 == SS_P16, so behaviour matches
  ; the pre-reserve world.
  CHECK_FOR_OUT_OF_MEMORY SS_PEND_P16
  RTS


; Store hash value at current heap location and advance heap
; On entry HT_V16 contains the value to store
;          MEMP16 points to where value should be stored
; On exit MEMP16 advanced past the value
;         Y = 0
;         X is preserved
;         A is not preserved
store_hash_value:
  LDY #$00
  LDA HT_V16
  APPEND_HEAPA
  LDA HT_V16 + 1
  APPEND_HEAPA
  JMP advance_heap     ; Tail call


  .ifdef LHASHTAB
select_label_hash_table:
  SET16 LHASHTAB, HTP16
  RTS
  .endif


select_instruction_hash_table:
  LDA #LABEL_TYPE_GLOBAL
  STA LABEL_TYPE       ; Clear local label flag for instruction lookup
  SET16 IHASHTAB, HTP16
  RTS
