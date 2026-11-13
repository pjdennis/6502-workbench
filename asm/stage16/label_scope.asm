; Label Scope Management (for macro expansions)
;
; Each macro expansion gets a unique scope for local labels. The scope is
; identified by EXPANSION_ID, which acts as a synthetic "global label pointer"
; for local label scoping. Since expansion IDs are small integers (1, 2, 3...),
; they won't conflict with real heap addresses.
;
; Scope state is saved on a dedicated scope stack (SCOPE_STACK in memory),
; NOT the 6502 stack. Each entry is 5 bytes:
;   - CURR_GLOBAL_HEAP_L
;   - CURR_GLOBAL_HEAP_H
;   - CACHED_HASH
;   - MACRO_ENTRY_L (macro hash table address for recursion detection)
;   - MACRO_ENTRY_H
;
; The scope stack grows upward from SCOPE_STACK.
;
; Requires (from caller):
;   SCOPE_STACK          - base address of scope stack
;   MACRO_ENTRY_L/H      - macro hash table entry address (set before push)
;
; Requires (from hash_table21.asm):
;   CURR_GLOBAL_HEAP_L/H - current global label heap address
;   CACHED_HASH          - pre-computed hash for current scope
;   scramble_table       - hash scrambling table


  .zeropage

EXPANSION_ID_L .data $00 ; 2-byte expansion counter for macro scopes
EXPANSION_ID_H .data $00 ; "
SCOPE_PTR_L    .data $00 ; Pointer to next free slot in scope stack
SCOPE_PTR_H    .data $00 ; "

  .code


; Initialize scope stack and expansion ID counter (call once at program start)
; On exit: SCOPE_PTR points to SCOPE_STACK (empty stack)
;          EXPANSION_ID_L/H = 0
;          A clobbered, X/Y preserved
init_scope_stack
  LDA #<SCOPE_STACK
  STA SCOPE_PTR_L
  LDA #>SCOPE_STACK
  STA SCOPE_PTR_H
  LDA #$00
  STA EXPANSION_ID_L
  STA EXPANSION_ID_H
  RTS


; Reset scope stack and expansion ID to initial state (call between passes)
; This ensures pass 2 uses the same scope IDs as pass 1
; On exit: SCOPE_PTR points to SCOPE_STACK (empty stack)
;          EXPANSION_ID_L/H = 0
;          A clobbered, X/Y preserved
reset_scope_stack
  LDA #<SCOPE_STACK
  STA SCOPE_PTR_L
  LDA #>SCOPE_STACK
  STA SCOPE_PTR_H
  LDA #$00
  STA EXPANSION_ID_L
  STA EXPANSION_ID_H
  RTS


; Push current label scope and create new macro expansion scope
; Saves CURR_GLOBAL_HEAP_L/H, CACHED_HASH, and MACRO_ENTRY_L/H to scope stack,
; increments EXPANSION_ID, sets up synthetic scope using expansion ID.
;
; On entry: MACRO_ENTRY_L/H contains the macro's hash table entry address
; On exit: New scope active (CURR_GLOBAL_HEAP = EXPANSION_ID, CACHED_HASH set)
;          Previous scope saved on scope stack
;          A, Y clobbered, X preserved
push_label_scope
  ; Bounds check: ensure room for one 5-byte entry
  ; Check if SCOPE_PTR > SCOPE_LIMIT - 5 (last valid position for 5-byte write)
  LDA SCOPE_PTR_H
  CMP #>SCOPE_LIMIT-$05
  BCC .scope_ok
  BNE .scope_overflow
  LDA SCOPE_PTR_L
  CMP #<SCOPE_LIMIT-$05
  BCC .scope_ok
  BEQ .scope_ok
.scope_overflow
  JMP err_macro_nesting_too_deep
.scope_ok
  ; Save current scope state to scope stack
  LDY #$00
  LDA CURR_GLOBAL_HEAP_L
  STA (SCOPE_PTR_L),Y
  INY
  LDA CURR_GLOBAL_HEAP_H
  STA (SCOPE_PTR_L),Y
  INY
  LDA CACHED_HASH
  STA (SCOPE_PTR_L),Y
  ; Save macro entry address for recursion detection
  INY
  LDA MACRO_ENTRY_L
  STA (SCOPE_PTR_L),Y
  INY
  LDA MACRO_ENTRY_H
  STA (SCOPE_PTR_L),Y
  ; Advance scope pointer by 5 bytes
  CLC
  LDA SCOPE_PTR_L
  ADC #$05
  STA SCOPE_PTR_L
  LDA SCOPE_PTR_H
  ADC #$00
  STA SCOPE_PTR_H
  ; Increment expansion ID
  INC EXPANSION_ID_L
  BNE .no_carry
  INC EXPANSION_ID_H
.no_carry
  ; Set CURR_GLOBAL_HEAP to expansion ID (synthetic scope pointer)
  LDA EXPANSION_ID_L
  STA CURR_GLOBAL_HEAP_L
  LDA EXPANSION_ID_H
  STA CURR_GLOBAL_HEAP_H
  ; Calculate CACHED_HASH from expansion ID
  ; Use low byte through scramble table for reasonable distribution
  LDA EXPANSION_ID_L
  AND #$7F
  TAY
  LDA scramble_table,Y
  STA CACHED_HASH
  RTS


; Pop label scope, restoring previous CURR_GLOBAL_HEAP and CACHED_HASH
; On exit: Previous scope restored from scope stack
;          A, Y clobbered, X preserved
pop_label_scope
  ; Move scope pointer back by 5 bytes
  SEC
  LDA SCOPE_PTR_L
  SBC #$05
  STA SCOPE_PTR_L
  LDA SCOPE_PTR_H
  SBC #$00
  STA SCOPE_PTR_H
  ; Restore scope state from scope stack
  LDY #$00
  LDA (SCOPE_PTR_L),Y
  STA CURR_GLOBAL_HEAP_L
  INY
  LDA (SCOPE_PTR_L),Y
  STA CURR_GLOBAL_HEAP_H
  INY
  LDA (SCOPE_PTR_L),Y
  STA CACHED_HASH
  RTS
