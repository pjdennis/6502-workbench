; Label Scope Management (for macro expansions)
;
; Each macro expansion gets a unique scope for local labels. The scope is
; identified by EXPANSION_ID, which acts as a synthetic "global label pointer"
; for local label scoping. Since expansion IDs are small integers (1, 2, 3...),
; they won't conflict with real heap addresses.
;
; Per-expansion activation state lives on the source stack as the trailing
; payload of each macro's memory frame. The payload tail (lowest-to-highest
; offset within the frame, ending at frame_size - 1) is:
;
;   LABEL_SCOPE16    lo/hi (2 bytes) - restored on pop
;   CACHED_HASH      (1 byte)        - restored on pop
;   prev_macro_lookup lo/hi (2 bytes) - restored on pop; threads the chain
;                                       of macro frames so resolve_identifier
;                                       can find the innermost macro frame in
;                                       O(1) via MACRO_LOOKUP_FRAME16
;   prev_macro_lookup_slots lo/hi (2 bytes)  - restored on pop; cached
;                                       slot[0] pointer kept in lockstep
;                                       with MACRO_LOOKUP_FRAME16
;   prev_macro_lookup_params lo/hi (2 bytes) - restored on pop; cached
;                                       param-name-list pointer kept in
;                                       lockstep with MACRO_LOOKUP_FRAME16
;   MACRO_ENTRY16    lo/hi (2 bytes) - saved but not restored (read by
;                                       check_macro_recursion to detect
;                                       recursive expansions). Sits at the
;                                       very end of the frame;
;                                       check_macro_recursion locates it via
;                                       frame_size - 2.
;
; expand_macro writes these 11 bytes (after the parameter slots) directly
; into the frame's reserved payload region after reserving via
; ss_reserve_frame -- there is no longer a staging buffer between the
; parser and the source-stack frame.
; pop_label_scope_from_frame (wired in as the source stack's
; MEMORY_POP_HANDLER compile-time equate in asm.asm) reads them back when
; the frame is popped.
;
; Pre-Phase-3.6 there was a separate SCOPE_STACK at $0400 with its own
; SCOPE_PTR16, push_label_scope, pop_label_scope, and a hard 51-entry
; ceiling (err_macro_nesting_too_deep). All of that is gone -- the limit
; on macro nesting is now plain source-stack OOM.
;
; Requires (from hash_table.asm):
;   LABEL_SCOPE16        - current scope for local label resolution
;   CACHED_HASH          - pre-computed hash for current scope
;
; Requires (from source_stack.asm):
;   SS_P16               - source stack pointer (read by
;                          pop_label_scope_from_frame to locate payload)

  .zeropage

EXPANSION_ID16:        .word ; 2-byte expansion counter for macro scopes
SCOPE_DEPTH:           .byte ; Current nesting depth (0 = not in macro);
                             ; read by labels.asm and expressions.asm to
                             ; pick local-label vs macro-local-label types
MACRO_LOOKUP_FRAME16:  .word ; Address of the innermost macro frame on the
                             ; source stack, or $0000 when no macro is
                             ; active. resolve_identifier uses this for
                             ; O(1) parameter-slot lookup instead of
                             ; walking the source stack each call.
MACRO_LOOKUP_SLOTS16:  .word ; Absolute address of slots[0] inside the
                             ; innermost macro frame -- equal to
                             ; MACRO_PAYLOAD_BASE16 at the moment
                             ; expand_macro commits. $0000 outside a
                             ; macro. Maintained in lockstep with
                             ; MACRO_LOOKUP_FRAME16; read by
                             ; ss_lookup_param_slot to avoid re-deriving
                             ; the slot offset on every call.
MACRO_LOOKUP_PARAMS16: .word ; Absolute address of the active macro
                             ; def's first parameter name -- equal to
                             ; (its MACRO_ENTRY16) + 1, skipping the
                             ; count byte. $0000 outside a macro.
                             ; Maintained in lockstep with
                             ; MACRO_LOOKUP_FRAME16; read by
                             ; ss_lookup_param_slot.
MACRO_PAYLOAD_BASE16:  .word ; Transient pointer used by expand_macro
                             ; during arg parsing. Points at
                             ; (SS_P16 - payload_size) -- the address
                             ; that becomes slot[0] once the frame is
                             ; pushed. Indirect-Y writes through it
                             ; populate slots and the scope tail without
                             ; needing a separate staging buffer.
MACRO_ARG_REMAIN:      .byte ; Args still to be parsed in expand_macro's
                             ; Phase 1 loop. Initialized from the count
                             ; byte at the start of the macro definition;
                             ; decremented per arg until 0.

  .code


; Initialize the scope-related counters. Called at program start and
; between passes so pass 2 reuses the same EXPANSION_IDs as pass 1.
; A clobbered, X/Y preserved.
init_scope_state:
  LDA #$00
  STA_LH16 EXPANSION_ID16
  STA SCOPE_DEPTH
  STA_LH16 MACRO_LOOKUP_FRAME16
  STA_LH16 MACRO_LOOKUP_SLOTS16
  STA_LH16 MACRO_LOOKUP_PARAMS16
  RTS


; Memory-source pop handler, wired in at compile time as the source
; stack's MEMORY_POP_HANDLER equate (asm.asm). Called from pop_source's
; curr_type=memory dispatch when a macro frame is popped. The frame's
; last 11 bytes hold the scope tail that expand_macro wrote into the
; reserved payload region:
;
;   tail offset 0..1:  prev LABEL_SCOPE16 lo/hi
;   tail offset 2:     prev CACHED_HASH
;   tail offset 3..4:  prev MACRO_LOOKUP_FRAME16 lo/hi
;   tail offset 5..6:  prev MACRO_LOOKUP_SLOTS16 lo/hi
;   tail offset 7..8:  prev MACRO_LOOKUP_PARAMS16 lo/hi
;   tail offset 9..10: MACRO_ENTRY16 (for recursion detection;
;                                     not restored on pop)
;
; Restores LABEL_SCOPE16, CACHED_HASH, and the lookup pointer triple
; (MACRO_LOOKUP_FRAME16 / _SLOTS16 / _PARAMS16); decrements SCOPE_DEPTH.
; The pop_source dispatch preserves Y/X around this call, so we can
; clobber them freely.
pop_label_scope_from_frame:
  LDY #0
  LDA (SS_P16),Y          ; frame_size
  SEC
  SBC #11                 ; offset of activation payload start
  TAY
  LDA (SS_P16),Y
  STA LABEL_SCOPE16
  INY
  LDA (SS_P16),Y
  STA LABEL_SCOPE16 + 1
  INY
  LDA (SS_P16),Y
  STA CACHED_HASH
  INY
  LDA (SS_P16),Y
  STA MACRO_LOOKUP_FRAME16
  INY
  LDA (SS_P16),Y
  STA MACRO_LOOKUP_FRAME16 + 1
  ; Restore the cached slot-list and param-list pointers in lockstep
  ; with MACRO_LOOKUP_FRAME16 -- the pointer-triple invariant.
  INY
  LDA (SS_P16),Y
  STA MACRO_LOOKUP_SLOTS16
  INY
  LDA (SS_P16),Y
  STA MACRO_LOOKUP_SLOTS16 + 1
  INY
  LDA (SS_P16),Y
  STA MACRO_LOOKUP_PARAMS16
  INY
  LDA (SS_P16),Y
  STA MACRO_LOOKUP_PARAMS16 + 1
  DEC SCOPE_DEPTH
  RTS
