; macro_expansion.asm - Macro invocation and expansion
;
; Provides: check_macro_recursion, expand_macro
;
; Requires:
;   CURR_CHAR (asm.asm alias; backing storage in source_stack.asm)
;   TOKEN, PASS (asm.asm)
;   IN_MACRO_DEF (macro_capture.asm)
;   MACRO_ENTRY16, OPERAND16, TEMP, MACRO_MAX_ARGS (asm.asm)
;   LABEL_SCOPE16, CACHED_HASH, scramble_table (hash_table.asm)
;   EXPANSION_ID16, SCOPE_DEPTH, MACRO_LOOKUP_FRAME16,
;     MACRO_PAYLOAD_BASE16, MACRO_ARG_REMAIN (label_scope.asm)
;   read_char (asm.asm alias; implemented in source_stack.asm)
;   check_for_end_of_line (tokenizer.asm)
;   parse_expression (expressions.asm)
;   select_label_hash_table (common.asm)
;   hash_add (hash_table.asm), store_hash_value (common.asm)
;   ss_reserve_frame, ss_commit_pending_frame, SS_P16,
;     SS_PAYLOAD_SIZE, SS_MEM_PTR16, SS_NAME, SS_SRC_TYPE_MEMORY
;     (source_stack.asm)
;   err_* (errors.asm)

  .code


; Check if the active macro is already being expanded somewhere up the
; macro-frame chain. Walks via the prev_macro_lookup linked list
; threaded through each macro frame's payload, comparing each saved
; MACRO_ENTRY16 against the active one. File frames are skipped for
; free -- they don't sit in the chain at all. Pre-step-1 this used
; ss_walk_frames_by_type; the linked-list walk is faster (no per-frame
; CMPI16 against SOURCE_STACK, no curr_type filter test) and more
; direct.
;
; On entry: MACRO_ENTRY16 = the macro's hash table entry address.
; On exit:  Returns normally if no recursion; jumps to err_recursive_macro
;           on match. TABP16, A, Y clobbered; X preserved.
check_macro_recursion:
  ; TABP16 walks the chain, starting at MACRO_LOOKUP_FRAME16 (the
  ; innermost macro frame, or $0000 outside any macro).
  LDA MACRO_LOOKUP_FRAME16
  STA TABP16
  LDA MACRO_LOOKUP_FRAME16 + 1
  STA TABP16 + 1
.cmr_loop:
  ; Empty chain (or end of chain) -> no recursion.
  LDA TABP16
  ORA TABP16 + 1
  BEQ .cmr_done
  ; Compare this frame's MACRO_ENTRY16 (last 2 bytes of frame) against
  ; the active one. Match -> recursive; report and abort.
  LDY #0
  LDA (TABP16),Y          ; frame_size
  SEC
  SBC #2                  ; offset of saved MACRO_ENTRY16 lo
  TAY
  LDA (TABP16),Y
  CMP MACRO_ENTRY16
  BNE .cmr_advance
  INY
  LDA (TABP16),Y
  CMP MACRO_ENTRY16 + 1
  BNE .cmr_advance
  JMP err_recursive_macro
.cmr_advance:
  ; Move to the parent macro frame via prev_macro_lookup. Layout
  ; (scope_block tail, low to high offset relative to frame end):
  ;   -11 LABEL_SCOPE16 lo
  ;   -10 LABEL_SCOPE16 hi
  ;    -9 CACHED_HASH
  ;    -8 prev_macro_lookup lo  <-- read here
  ;    -7 prev_macro_lookup hi
  ;    -6..-3 reserved (MACRO_LOOKUP_SLOTS16 / _PARAMS16, filled
  ;           in phase 3)
  ;    -2 MACRO_ENTRY16 lo
  ;    -1 MACRO_ENTRY16 hi
  ; We arrive here from either the lo-byte or hi-byte BNE on
  ; MACRO_ENTRY16, so Y is frame_size - 2 or frame_size - 1 -- not a
  ; reliable base for prev_macro_lookup. Recompute the offset from
  ; frame_size directly. (Earlier the code did SBC #3 from a wrongly-
  ; assumed-fixed Y; the lo-byte path silently produced frame_size - 5,
  ; corrupting TABP16 with garbage.)
  LDY #$00
  LDA (TABP16),Y          ; frame_size
  SEC
  SBC #$08                ; offset of prev_macro_lookup lo
  TAY
  LDA (TABP16),Y
  PHA                     ; stash new TABP16 lo byte
  INY
  LDA (TABP16),Y          ; new TABP16 hi byte
  STA TABP16 + 1
  PLA
  STA TABP16
  JMP .cmr_loop
.cmr_done:
  RTS


; Look up TOKEN's identifier in the parameter slots of the active
; macro frame, using the cached MACRO_LOOKUP_PARAMS16 (def's param-
; name list) and MACRO_LOOKUP_SLOTS16 (slot[0] address) zp pointers.
; Walks the param-name list to find a matching index, then reads the
; corresponding slot.
;
; The cached pointers are maintained in lockstep with
; MACRO_LOOKUP_FRAME16 by expand_macro's commit path and
; pop_label_scope_from_frame -- so this routine doesn't need to
; re-derive them from the frame on every call.
;
; On entry: TOKEN holds the identifier; MACRO_LOOKUP_SLOTS16 and
;           MACRO_LOOKUP_PARAMS16 point into the active macro frame
;           (gated by SCOPE_DEPTH > 0 at the caller).
; On exit:  C=0 if found -- HEX16 (= OPERAND16) and IS_FWDREF set,
;             matching find_in_hash's contract.
;           C=1 if no parameter matched. HEX16/IS_FWDREF unchanged.
;           A, Y, HTTP16, TEMP clobbered. X preserved (the output
;             file handle in macro bodies, the activation byte index
;             in expand_macro Phase 1's nested-arg-parse path).
ss_lookup_param_slot:
  ; Save X -- callers depend on X surviving identifier lookup.
  TXA
  PHA
  ; HTTP16 := MACRO_LOOKUP_PARAMS16 - 1 (the def's count byte, which
  ; sits one byte before param1). Read N at offset 0, then INC HTTP16
  ; back to MACRO_LOOKUP_PARAMS16 for the param-name walk.
  SEC
  LDA MACRO_LOOKUP_PARAMS16
  SBC #1
  STA HTTP16
  LDA MACRO_LOOKUP_PARAMS16 + 1
  SBC #0
  STA HTTP16 + 1
  LDY #0
  LDA (HTTP16),Y                 ; A = N (count byte)
  TAX                             ; X = remaining param iterations
  ; Advance HTTP16 past the count byte to land on param1's first byte.
  INC HTTP16
  BNE .params_loaded
  INC HTTP16 + 1
.params_loaded:
  ; Slot offset starts at 0; slots are at MACRO_LOOKUP_SLOTS16[0..3*N).
  LDA #0
  STA TEMP                       ; TEMP = current slot offset
  ; Walk the param-name list. X is the number of names still to check;
  ; on each miss, advance HTTP16 past the null terminator, bump TEMP by
  ; 3 (next slot), and DEX. Termination is count-driven (no trailing
  ; empty-string sentinel in the def).
.lps_iter:
  CPX #0
  BEQ .lps_not_found             ; walked all N names without a match
  LDY #0
.lps_cmp:
  LDA (HTTP16),Y
  CMP TOKEN,Y
  BNE .lps_skip
  CMP #0
  BEQ .lps_match
  INY
  BNE .lps_cmp                    ; tokens are < 256 chars
.lps_skip:
  ; Names differ. Advance past this param's null and try the next one.
  ; Y indexes into the param name; walk to its null.
.lps_to_null:
  LDA (HTTP16),Y
  BEQ .lps_past_null
  INY
  BNE .lps_to_null
.lps_past_null:
  TYA
  SEC                             ; +1 to skip the null
  ADCA16 HTTP16, HTTP16
  ; slot offset += 3
  LDA TEMP
  CLC
  ADC #3
  STA TEMP
  DEX
  JMP .lps_iter
.lps_match:
  ; Slot at offset TEMP holds [fwdref, value_L, value_H], indexed
  ; through the cached MACRO_LOOKUP_SLOTS16 (= absolute address of
  ; slot[0] in the active macro frame).
  LDY TEMP
  LDA (MACRO_LOOKUP_SLOTS16),Y
  STA IS_FWDREF
  INY
  LDA (MACRO_LOOKUP_SLOTS16),Y
  STA HEX16
  INY
  LDA (MACRO_LOOKUP_SLOTS16),Y
  STA HEX16 + 1
  ; Restore X and return C=0 (found).
  PLA
  TAX
  CLC
  RTS
.lps_not_found:
  PLA
  TAX
  SEC
  RTS


; Expand a macro invocation
; On entry: MACRO_DEF_PTR points to the macro entry
;           ([N], param1\0, ..., paramN\0, body\0)
;           TOKEN contains the macro name
; On exit: Memory source pushed
expand_macro:
  ; Save original macro entry address before MACRO_DEF_PTR is modified
  CP16 MACRO_DEF_PTR16, MACRO_ENTRY16
  ; Check for recursive macro invocation
  JSR check_macro_recursion
  ; Save X (output file handle); reused below as the byte cursor while
  ; writing parsed slots into the future frame's payload area.
  TXA
  PHA

  ; Read N (the count byte) from the def. MACRO_MAX_ARGS was validated
  ; at definition time, so we don't recheck here.
  LDY #$00
  LDA (MACRO_DEF_PTR16),Y
  STA MACRO_ARG_REMAIN
  ; Advance MACRO_DEF_PTR past the count byte so the param-name walk
  ; below sees param1 at offset 0. After parsing every arg
  ; MACRO_DEF_PTR16 lands directly on the body's first byte (no
  ; terminator to skip).
  CLC
  LDA MACRO_DEF_PTR16
  ADC #$01
  STA MACRO_DEF_PTR16
  LDA MACRO_DEF_PTR16 + 1
  ADC #$00
  STA MACRO_DEF_PTR16 + 1

  ; Compute payload_size = 3*N + 11. TEMP = 3*N is used twice below
  ; (frame-size check + slot-base computation).
  ; Payload = N slots (3 bytes each) + 11-byte scope tail
  ; (LABEL_SCOPE16, CACHED_HASH, prev_macro_lookup,
  ;  prev_macro_lookup_slots, prev_macro_lookup_params, MACRO_ENTRY16).
  LDA MACRO_ARG_REMAIN
  ASL                       ; 2N
  CLC
  ADC MACRO_ARG_REMAIN      ; 3N
  STA TEMP                  ; TEMP = 3N (survives parse_expression)
  CLC
  ADC #$0B                  ; A = 3N + 11 = payload_size
  STA SS_PAYLOAD_SIZE       ; reservation size for ss_reserve_frame

  ; Frame_size = 19 + name_len + 3*N (8 fixed header + 11-byte scope
  ; tail). If > 255, raise err_too_many_arguments. With cap = 32 and
  ; the 127-char TOKEN limit, worst case is 19 + 127 + 96 = 242 --
  ; well under 256 -- so the runtime guard below is dead code today
  ; but kept as defense in case MACRO_MAX_ARGS is ever raised.
  LDY #$FF
.measure_name:
  INY
  LDA SS_NAME,Y
  BNE .measure_name
  TYA
  CLC
  ADC TEMP                  ; A = name_len + 3N
  BCC .frame_size_check_2
  JMP .too_many
.frame_size_check_2:
  CLC
  ADC #$13                  ; A = 19 + name_len + 3N
  BCC .frame_size_ok
  JMP .too_many             ; would overflow frame_size byte
.frame_size_ok:

  ; Compute MACRO_PAYLOAD_BASE16 = SS_P16 - payload_size BEFORE the
  ; reserve call (ss_reserve_frame zeroes SS_PAYLOAD_SIZE on exit, and
  ; SS_P16 doesn't move during reserve, so this value stays valid
  ; through the parse loop).
  ;
  ; The future payload region sits at (SS_P16 - payload_size)..(SS_P16
  ; - 1) once the frame commits. Until commit that range is the top
  ; of the pending region (still safely below SS_P16); heap can't
  ; reach it because advance_heap's OOM check is now against
  ; SS_PEND_P16, which after the reserve sits below the payload.
  ;
  ; Crucially, SS_P16 / SS_SRC_TYPE / SS_MEM_PTR16 / SS_CURR_LINE16
  ; are unchanged during arg parsing -- the parent's source stays
  ; active so read_char keeps reading args from where the invocation
  ; sits, and any error during arg parsing reports the correct
  ; line / source.
  SEC
  LDA SS_P16
  SBC SS_PAYLOAD_SIZE
  STA MACRO_PAYLOAD_BASE16
  LDA SS_P16 + 1
  SBC #$00
  STA MACRO_PAYLOAD_BASE16 + 1

  ; Reserve the pending frame. ss_reserve_frame does its own OOM
  ; check, copies SS_NAME (= TOKEN, the macro name) into the pending
  ; region's name field at offset 7+, and zeroes SS_PAYLOAD_SIZE on
  ; exit. After this, parse_expression / read_token may freely clobber
  ; TOKEN -- the captured name lives in the pending frame.
  LDA #SS_SRC_TYPE_MEMORY
  JSR ss_reserve_frame

  ; ----- Phase 1: parse args, writing slots into (MACRO_PAYLOAD_BASE16) -----
  ;
  ; X = byte offset within the payload region for the next slot. X is
  ; preserved across parse_expression (find_in_hash and
  ; ss_lookup_param_slot both preserve it), so it survives the loop
  ; without explicit save/restore.
  LDX #$00
.parse_loop:
  LDA MACRO_ARG_REMAIN
  BEQ .parse_done
  ; Skip past parameter name in the def
  LDY #$FF
.skip_param:
  INY
  LDA (MACRO_DEF_PTR16),Y
  BNE .skip_param
  TYA
  SEC                       ; +1 for the null
  ADCA16 MACRO_DEF_PTR16, MACRO_DEF_PTR16
  ; Check that an argument is present
  JSR check_for_end_of_line
  BCC .have_arg
  JMP err_too_few_arguments
.have_arg:
  ; Parse argument expression in PARENT'S scope (MACRO_LOOKUP_FRAME16
  ; still points at the parent macro frame, or $0000 at top level).
  JSR parse_expression
  ; Write slot at (MACRO_PAYLOAD_BASE16)[X..X+2] = [fwdref, value_L, value_H]
  TXA
  TAY
  LDA IS_FWDREF
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA OPERAND16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA OPERAND16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y
  ; Advance X past this slot
  INX
  INX
  INX
  ; Decrement remaining; if 0, last arg consumed.
  DEC MACRO_ARG_REMAIN
  BEQ .parse_done
  ; More params expected - require comma
  JSR check_for_end_of_line
  BCS .too_few_next
  CMP #','
  BNE .arg_err_comma
  JSR read_char
  JMP .parse_loop
.too_few_next:
  JMP err_too_few_arguments
.arg_err_comma:
  JMP err_comma_expected
.parse_done:
  ; No extra args allowed
  JSR check_for_end_of_line
  BCS .args_done_ok
  JMP .too_many
.args_done_ok:
  ; ----- Write parent's scope state into the scope_block region -----
  ;
  ; X currently equals 3*N (the scope-block offset within the payload)
  ; because we INX'd 3 per arg. Point Y at it for the indirect-Y
  ; stores below.
  ;
  ; Layout (offsets relative to scope_block start = 3*N):
  ;   0..1 : prev LABEL_SCOPE16
  ;   2    : prev CACHED_HASH
  ;   3..4 : prev MACRO_LOOKUP_FRAME16
  ;   5..6 : prev MACRO_LOOKUP_SLOTS16
  ;   7..8 : prev MACRO_LOOKUP_PARAMS16
  ;   9..10: MACRO_ENTRY16 (recursion detection; at the very end so
  ;          check_macro_recursion's frame_size-2 anchor still works)
  TXA
  TAY
  LDA LABEL_SCOPE16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA LABEL_SCOPE16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA CACHED_HASH
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_FRAME16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_FRAME16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_SLOTS16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_SLOTS16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_PARAMS16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_LOOKUP_PARAMS16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_ENTRY16
  STA (MACRO_PAYLOAD_BASE16),Y
  INY
  LDA MACRO_ENTRY16 + 1
  STA (MACRO_PAYLOAD_BASE16),Y

  ; ----- Switch to the new scope -----
  ;
  ; Done AFTER scope_block is captured so the saved values are the
  ; parent's, not the new ones.
  INC16 EXPANSION_ID16
  CP16 EXPANSION_ID16, LABEL_SCOPE16
  LDA EXPANSION_ID16
  AND #$7F
  TAY
  LDA scramble_table,Y
  STA CACHED_HASH
  INC SCOPE_DEPTH

  ; ----- Commit the pending frame -----
  ;
  ; ss_commit_pending_frame writes prev_data at fixed offsets 5..6
  ; from parent's CURRENT SS_MEM_PTR16 / SS_CURR_FILE (so a memory
  ; parent's cursor advance during arg parsing is captured at the
  ; right moment), advances SS_P16 := SS_PEND_P16, sets SS_SRC_TYPE
  ; := MEMORY (the new frame's curr_type at offset 1), and resets
  ; SS_CURR_LINE16. The payload region we wrote above was already in
  ; place before commit and is left untouched.
  JSR ss_commit_pending_frame

  ; Anchor MACRO_LOOKUP_FRAME16 at the new top frame so identifier
  ; lookups inside the body resolve from this frame's slots.
  LDA SS_P16
  STA MACRO_LOOKUP_FRAME16
  LDA SS_P16 + 1
  STA MACRO_LOOKUP_FRAME16 + 1

  ; Cache the slot-list and param-list pointers so ss_lookup_param_slot
  ; doesn't have to re-derive them on every call inside the body.
  ; MACRO_PAYLOAD_BASE16 still holds slot[0] from the parse-loop
  ; setup; MACRO_ENTRY16 still holds the def's count-byte address.
  ; These two writes are in lockstep with MACRO_LOOKUP_FRAME16 above
  ; and with their counterparts in pop_label_scope_from_frame; the
  ; pointer-triple invariant lives across the three sites.
  LDA MACRO_PAYLOAD_BASE16
  STA MACRO_LOOKUP_SLOTS16
  LDA MACRO_PAYLOAD_BASE16 + 1
  STA MACRO_LOOKUP_SLOTS16 + 1
  CLC
  LDA MACRO_ENTRY16
  ADC #1
  STA MACRO_LOOKUP_PARAMS16
  LDA MACRO_ENTRY16 + 1
  ADC #0
  STA MACRO_LOOKUP_PARAMS16 + 1

  ; Install body pointer. The arg loop advanced MACRO_DEF_PTR16 past
  ; every param name; it now sits on the body's first byte.
  CP16 MACRO_DEF_PTR16, SS_MEM_PTR16

  ; Restore X (output file handle)
  PLA
  TAX
  RTS
.too_many:
  JMP err_too_many_arguments
