; ============================================================================
; ASM17 - Self-Hosting 6502 Assembler
; ============================================================================
;
; See README for architecture, memory map, and module documentation.
;
; This file: memory layout constants, zero page variables, module includes,
;            assembly loop, entry point, reset/interrupt vectors.
;
; ============================================================================

; Addresses
FWDREF_LIST     = $0200  ; Forward reference list (512 bytes, $0200-$03FF)
FWDREF_LIMIT    = FWDREF_LIST + $0200 ; Limit for forward reference list data
                         ; $0400-$04FF: free.
                         ;   - First half ($0400-$047F) was SCOPE_STACK
                         ;     pre-Phase-3.6 (activation state moved to the
                         ;     source-stack frame's payload).
                         ;   - Second half ($0480-$04FF) was MACRO_NAME_SAVE,
                         ;     a 128-byte buffer expand_macro used to stash
                         ;     the macro name across arg parsing. Reclaimed
                         ;     once expand_macro switched to ss_reserve_frame
                         ;     (which captures the name BEFORE arg parsing
                         ;     into the pending frame's name region) +
                         ;     ss_commit_pending_frame.
                         ; $0500-$05FF was MACRO_ARG_BUF pre-Phase-4.8;
                         ; reclaimed when activation slots moved into the
                         ; source stack frame.
                         ; $0690-$06AF was MACRO_ACTIVATION (the activation-
                         ; payload staging buffer) until expand_macro switched
                         ; to writing parsed slots directly into the new
                         ; macro frame's payload region. Now free.
TOKEN           = $0600  ; Buffer for the current token being read
ELSE_SEEN_ARRAY = $0680  ; Array tracking .else seen per nesting level
                         ; (16 bytes, $0680-$068F, all used). Accessed
                         ; as ELSE_SEEN_ARRAY - 1,Y with Y = COND_DEPTH
                         ; (1..16), so depth d maps to entry d-1 with no
                         ; runtime index adjustment. Y is never 0 at an
                         ; access site, so the biased base's byte at
                         ; $067F (TOKEN's last byte) is never touched.
MACRO_MAX_ARGS  = $20    ; Hard cap on parameters per macro definition (32).
                         ; Set deliberately well below what the 1-byte
                         ; frame_size could otherwise allow, so the
                         ; max-args ceiling is INDEPENDENT of macro
                         ; name length -- a macro author doesn't have
                         ; to think about whether their name length
                         ; eats into their arg budget. Worst case at
                         ; this cap (using the 127-char TOKEN limit
                         ; as the name) is 19 + 127 + 96 = 242 bytes
                         ; (frame_size = 19 + name_len + 3*N: 8-byte
                         ; fixed header + 11-byte scope tail),
                         ; comfortably under the 256-byte frame_size
                         ; ceiling. expand_macro's runtime frame-size
                         ; guard remains in place as defense in case
                         ; this constant is ever raised again.
LHASHTAB        = $0700  ; Label hash table
IFDEF_DECISIONS = $0800  ; Buffer for .ifdef decisions (256 bytes)
*               = $2000  ; Code generates here follwed by HEAP
SOURCE_STACK      = $F000  ; Source stack will grow down from 1 below here


  .zeropage

; Zero page locations
TEMP:            .byte        ; 1 byte
PC16:            .word        ; 2 byte program counter
HEX16:           .word        ; 2 byte hex value, also aliased as OPERAND16
OPERAND16 = HEX16             ; Operand value - alias for HEX16
PASS:            .byte        ; 1 byte $00 = pass 1 $FF = pass 2
STARTED:         .byte        ; flag to indicate output has started
CURR_OUT_FILE:   .byte        ; Current output file (for closing on error)
IN_ZEROPAGE:     .byte        ; Flag indicating if in zero page section
PC_SAVE16:       .word        ; Save location for PC when switching sections
INST_PTR16:      .word        ; Pointer to instruction mode table entry, aliased as MACRO_DEF_PTR16
MACRO_DEF_PTR16 = INST_PTR16  ; Heap pointer where macro body is being stored, aliased to INST_PTR16
IS_FWDREF:       .byte        ; $FF if current label is forward ref (pass 1 only)
MACRO_ENTRY16:   .word        ; Original macro hash entry address (for recursion check)

  .ifdef enable_debug
DEBUG_FLAG:      .byte        ; Non-zero if debug output enabled
PASS_1_FWDREF16: .word        ; Forward ref pointer after pass 1
SMALL_HEAP_FLAG: .byte        ; Non-zero if small_heap argument was passed
SHOW_MACROS:     .byte        ; Non-zero if captured macro definitions should be printed
MACRO_PTR16:     .word        ; Pointer to macro name (for show_captured_macros)
  .endif

  .code


; Include files
  .include out/inst.asm.out   ; This goes first since the tables should start on a page boundary
  .include environment.asm
  .include macros.asm
  .include common.asm
  .include label_scope.asm
  .include forward_ref.asm
SS_NAME             = TOKEN
MEMORY_POP_HANDLER  = pop_label_scope_from_frame  ; called by pop_source
                                                   ; on memory frames; restores
                                                   ; the macro's saved scope
  .include source_stack.asm
read_char          = source_stack_read_char
CURR_CHAR          = SS_CURR_CHAR
CURR_LINE16        = SS_CURR_LINE16
  .include errors.asm
  .ifdef enable_debug
SS_ERR_NO_FILE     = err_no_file   ; after errors.asm: an assignment takes
                                   ; only labels defined before it
  .endif
  .include from_decimal.asm
  .include output.asm
  .include tokenizer.asm
  .include expressions.asm
  .include labels.asm
  .include instructions.asm
  .include directives.asm
  .include macro_capture.asm
  .include macro_expansion.asm


; ============================================================================
; ASSEMBLY LOOP
; ============================================================================

; Read from input, assemble code and write to output
; On entry PASS indicates the current pass:
;            bit 7 clear = pass 1
;            bit 7 set = pass 2
;          X contains the file handle of the output file
; On exit X is preserved
;         A, Y are not preserved
assemble_code:
  LDA #$00
  STA STARTED
  STA IN_ZEROPAGE
  STA_LH16 PC16
  STA_LH16 PC_SAVE16
  STA_LH16 CURR_LINE16
  STA_LH16 LABEL_SCOPE16 ; Initialize scope (0 = no global yet)
  STA LABEL_TYPE         ; Initialize local label flag
  STA COND_DEPTH         ; Clear conditional depth
  STA SKIP_DEPTH         ; Clear skip depth
  STA IN_MACRO_DEF       ; Clear macro definition flag
  STA IFDEF_INDEX        ; Clear .ifdef decision index
  ; Clear ELSE_SEEN_ARRAY (16 bytes, one per COND_DEPTH level 1..16,
  ; through the same -1 biased access the use sites employ). BNE stops
  ; the loop after Y=1 so the bias byte at $067F is not written.
  LDY #16
.clear_else_seen:
  STA ELSE_SEEN_ARRAY - 1,Y
  DEY
  BNE .clear_else_seen
.line_loop:
  JSR read_char
  BCC .character_read
  ; End of input - check for unclosed conditional
  LDA COND_DEPTH
  BEQ .no_unclosed_ifdef
  JMP err_unclosed_ifdef
.no_unclosed_ifdef:
  ; Check for unclosed macro definition
  LDA IN_MACRO_DEF
  BEQ .no_unclosed_macro
  JMP err_unclosed_macro
.no_unclosed_macro:
  RTS
.character_read:
  INC16 CURR_LINE16
  ; Check if we're capturing macro body
  LDY IN_MACRO_DEF
  BEQ .not_capturing_macro
  JSR capture_macro_line
  JMP .line_loop
.not_capturing_macro:
  ; Check if we're skipping (conditional assembly)
  LDY SKIP_DEPTH
  BEQ .not_skipping
  ; --- Skipping mode: only process .ifdef/.ifndef/.else/.endif ---
  CMP #' '
  BNE .skip_not_space
  ; Line starts with space - skip spaces to find directive
  JSR check_for_end_of_line
  BCS .line_loop
  JMP .skip_check_directive
.skip_not_space:
  JSR check_for_end_of_line
  BCS .line_loop
  ; Line starts with non-space - skip label, check for directive
  JSR skip_token
  JSR check_for_end_of_line
  BCS .line_loop
.skip_check_directive:
  CMP #'.'
  BNE .skip_line
  ; It's a directive - only process ifdef/ifndef/else/endif
  JSR read_char
  JSR read_token
  JSR process_conditional_directive
  BCC .back_to_line_loop ; directive processed; already skipped line
.skip_line:
  JSR skip_rest_of_line
  JMP .line_loop
.not_skipping:
  CMP #' '
  BEQ .line_starts_with_space
  JSR check_for_end_of_line
  BCS .back_to_line_loop
  JSR capture_label
  BCC .check_for_opcode
  BCS .back_to_line_loop   ; Always taken
.line_starts_with_space:
  JSR check_for_end_of_line
  BCS .back_to_line_loop
.check_for_opcode:
  CMP #'.'
  BNE .opcode
; Directive
.directive:
  JSR read_char
  JSR process_directive
  LDA CURR_CHAR
  CMP #'.'
  BEQ .directive            ; Another directive on same line
  JMP .line_loop
.opcode:
  ; Read mnemonic and look up in instruction table
  JSR lookup_mnemonic      ; Returns with C=0 for mnemonic or C=1 for macro
  ; A contains current char after mnemonic or macro name
  BCS .macro
  ; Parse operand to capture value and determine addressing mode
  JSR parse_operand
  ; Emit the instruction
  JSR emit_instruction 
  ; A contains current char after operand - check for garbage
  ; Skip trailing spaces, then check for end of line (handles comments)
  JSR check_for_end_of_line
  BCS .back_to_line_loop
  JMP err_unexpected_text
.macro:
  JSR expand_macro
.back_to_line_loop:
  JMP .line_loop


  .include init.asm


; ============================================================================
; ENTRY POINT
; ============================================================================

; Entry point
start:
  .ifdef enable_test_runner
  JMP test_runner_start
  .endif
  ; Initialize output file handle to 0
  LDA #$00
  STA CURR_OUT_FILE
  .ifdef enable_debug
  ; Initialize debug flags to 0
  STA DEBUG_FLAG
  STA SMALL_HEAP_FLAG
  STA SHOW_MACROS
  .endif
  ; Initialize source stack early so interrupt handler works correctly.
  ; The memory-source pop hook (pop_label_scope_from_frame) is wired in
  ; at compile time via the MEMORY_POP_HANDLER equate above; no runtime
  ; install step is needed.
  JSR source_stack_init
  ; Initialize scope state (EXPANSION_ID, SCOPE_DEPTH).
  JSR init_scope_state
  ; Check argument count (must be at least 2)
  JSR argc
  CMP #$02
  BCC .err_usage         ; Less than 2 args
  STA ARG_COUNT          ; Save total arg count
  ; Initialize heap and hash table early for define: args
  JSR init_heap
  JSR select_label_hash_table
  JSR init_hash_table
  ; Process arguments 2 onwards (arg 0 = input, arg 1 = output)
  LDY #$02               ; Argument index
.arg_loop:
  CPY ARG_COUNT
  BCS .args_done         ; Processed all args
  TYA                    ; Argument index
  JSR argv               ; Get arg[Argument index]
  STAX16 TABP16
  JSR match_command_line_arg
  BCS .invalid_argument  ; Match not found
  INY                    ; Move to next argument
  BNE .arg_loop          ; Always taken. TODO: if this wraps raise a too many arguments error
.invalid_argument:
  JMP err_invalid_arg
.err_usage:
  JMP err_usage
.args_done:
  LDA #$00
  STA PASS            ; Bit 7 = 0 (pass 1)
  JSR init_fwdref_list
  JSR open_input

  ; Open output file
  LDA #1
  JSR argv
  JSR openout
  STA CURR_OUT_FILE
  TAX

  JSR assemble_code
  JSR finalize_fwdref_list

  .ifdef enable_debug
  ; Capture forward ref pointer after pass 1
  CP16 FWDREF16, PASS_1_FWDREF16
  .endif

  LDA #$FF
  STA PASS            ; Bit 7 = 1 (pass 2)
  JSR reset_fwdref_ptr
  JSR init_scope_state    ; Reset so pass 2 uses same scope IDs as pass 1
  JSR open_input
  JSR assemble_code

  .ifdef enable_debug
  ; Verify forward ref pointer matches pass 1
  CMP16 FWDREF16, PASS_1_FWDREF16
  BEQ .fwdref_ok
  ; Mismatch in ref counts
  JMP err_fwdref_tracking
.fwdref_ok:
  .endif

  ; Close output file
  TXA
  JSR close
  LDA #$00
  STA CURR_OUT_FILE

  .ifdef enable_debug
  ; Print heap usage if debug flag is set
  LDA DEBUG_FLAG
  BEQ .skip_debug_output
  SHOW_MESSAGEI msg_heap_used
  ; Calculate heap used: MEMP16 - HEAP
  SEC
  SBCI16 MEMP16, HEAP, TO_DECIMAL_VALUE16
  JSR show_decimal
  SHOW_MESSAGEI msg_bytes
  ; Print forward reference count
  SHOW_MESSAGEI msg_fwdref_count
  ; Calculate forward ref count: (PASS_1_FWDREF16 - FWDREF_LIST) / 2
  SEC
  SBCI16 PASS_1_FWDREF16, FWDREF_LIST, TO_DECIMAL_VALUE16
  ; Divide by 2 (16-bit right shift)
  LSR16 TO_DECIMAL_VALUE16
  JSR show_decimal
  SHOW_CHAR '\n'
.skip_debug_output:
  .endif

  ; All done, successfully
  BRK
  .byte 0               ; Success code


  .ifdef enable_debug
msg_heap_used:
  .asciiz "Heap used: "
msg_bytes:
  .asciiz " bytes\n"
msg_fwdref_count:
  .asciiz "Forward references forced to absolute: "
  .endif


  .ifdef enable_test_runner
  .include test_runner.asm
  .endif

HEAP:                   ; Heap goes after the program code


* = $FFFC
  .word start           ; Reset vector
  .word interrupt       ; Interrupt vector
