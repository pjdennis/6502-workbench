; Addressing mode operand number of bytes
OPERAND_BYTES_0 = $10
OPERAND_BYTES_1 = $20
OPERAND_BYTES_2 = $40

; Addressing mode constants
MODE_NONE  = $00+OPERAND_BYTES_0 ; Implied (no operand)
MODE_IMM   = $01+OPERAND_BYTES_1 ; Immediate
MODE_ZP    = $02+OPERAND_BYTES_1 ; Zero page
MODE_ZPX   = $03+OPERAND_BYTES_1 ; Zero page, X
MODE_ZPY   = $04+OPERAND_BYTES_1 ; Zero page, Y
MODE_ABS   = $05+OPERAND_BYTES_2 ; Absolute
MODE_ABSX  = $06+OPERAND_BYTES_2 ; Absolute, X
MODE_ABSY  = $07+OPERAND_BYTES_2 ; Absolute, Y
MODE_INDX  = $08+OPERAND_BYTES_1 ; Indirect, X - ($zp,X)
MODE_INDY  = $09+OPERAND_BYTES_1 ; Indirect, Y - ($zp),Y
MODE_REL   = $0A+OPERAND_BYTES_1 ; Relative (branches)
MODE_IND   = $0B+OPERAND_BYTES_2 ; Indirect - JMP ($xxxx)
MODE_MACRO = $8E                 ; Sentinel marker to indicate macro
MODE_END   = $8F                 ; Terminates the list of modes

; Label type constants (for LABEL_TYPE variable in hash table operations)
LABEL_TYPE_GLOBAL = $00   ; Global label (no escape format)
LABEL_TYPE_LOCAL  = $01   ; Local label under global scope (heap address)
LABEL_TYPE_MACRO  = $02   ; Macro parameter (expansion ID)
LABEL_TYPE_MACRO_LOCAL = $03 ; Macro-local label (expansion ID)

HT_KEY = TOKEN
HT_V16 = HEX16


  .zeropage

MEMP16:          .data $0000 ; 2 byte heap pointer

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
; On entry: fs_ptr = file stack pointer to check against MEMP16
; Raises err_out_of_memory if fs_ptr - MEMP16 < 256
; On exit: A not preserved, X and Y preserved
  .macro CHECK_FOR_OUT_OF_MEMORY fs_ptr
  ; Quick check: if ptr_H - MEMP16_H > 1, we have >= 512 bytes free
  LDA fs_ptr+$01
  SEC
  SBC MEMP16+$01        ; A = high byte difference
  CMP #$02
  BCS .oom_ok           ; >= 2 means >= 512 bytes, definitely safe
  ; High bytes are close (differ by 0 or 1) - do precise check
  ; Check: ptr - MEMP16 >= 256 (high byte of difference must be non-zero)
  LDA fs_ptr
  SEC
  SBC MEMP16            ; Low byte of difference (result discarded, need borrow)
  LDA fs_ptr+$01
  SBC MEMP16+$01        ; A = high byte of (ptr - MEMP16)
  BNE .oom_ok           ; Non-zero means >= 256 bytes free
  JMP err_out_of_memory
.oom_ok:
  .endmacro


init_heap:
  .ifdef enable_debug
  LDA SMALL_HEAP_FLAG
  BEQ .normal_heap
  ; Small heap for testing: only ~384 bytes available
  SET16 FILE_STACK-$0180 MEMP16
  RTS
.normal_heap:
  .endif
  SET16 HEAP MEMP16
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
  INC MEMP16+$01
.done:
  ; Check for collision with file stack
  CHECK_FOR_OUT_OF_MEMORY FS_P16
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
  STA (MEMP16),Y
  INY
  LDA HT_V16+$01
  STA (MEMP16),Y
  INY
  JMP advance_heap     ; Tail call


select_instruction_hash_table:
  LDA #LABEL_TYPE_GLOBAL
  STA LABEL_TYPE       ; Clear local label flag for instruction lookup
  SET16 IHASHTAB HTP16
  RTS
