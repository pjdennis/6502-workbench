; Forward reference list management
; List is stored at FWDREF_LIST, terminated by $FFFF
; Each entry is 2 bytes (PC low, PC high) of an instruction with forward ref
;
; Requires:
;   FWDREF_LIST  - start address of forward reference list
;   FWDREF_LIMIT - max pointer value before adding (room for entry + terminator)
;   PCL;PCH      - zero page locations containing program counter
;   err_too_many_forward_refs - error handler for list overflow

  .zeropage

FWDREF_L    .data $00 ; Pointer to forward reference list (low)
FWDREF_H    .data $00 ; Pointer to forward reference list (high)

  .code


; Initialize forward reference list pointer (call at start of pass 1)
; Reset forward reference pointer (call at start of pass 2)
; On exit: A is not preserved
;          X, Y are preserved
init_fwdref_list
reset_fwdref_ptr
  LDA #<FWDREF_LIST
  STA FWDREF_L
  LDA #>FWDREF_LIST
  STA FWDREF_H
  RTS


; Finalize forward reference list (call at end of pass 1)
; Writes $FFFF terminator at current pointer position
; On exit: A, Y are not preserved
;          X is preserved
finalize_fwdref_list
  LDY #$00
  LDA #$FF
  STA (FWDREF_L),Y
  INY
  STA (FWDREF_L),Y
  RTS


; Add current PC to forward reference list (call in pass 1 when label not found)
; On exit: A, Y are not preserved
;          X is preserved
;          Jumps to err_too_many_forward_refs if list is full
add_forward_ref
  ; Check if there's room (pointer must be < FWDREF_LIMIT - 2) to allow for terminator
  LDA FWDREF_H
  CMP #>FWDREF_LIMIT-$02
  BCC .ok                 ; High byte < limit high, definitely ok
  BNE .too_many           ; High byte > limit high, definitely too many
  ; High byte equals limit high, check low byte
  LDA FWDREF_L
  CMP #<FWDREF_LIMIT-$02
  BCS .too_many           ; >= FWDREF_LIMIT, no room for entry + terminator
.ok
  ; Store PC at current list position
  LDY #$00
  LDA PCL
  STA (FWDREF_L),Y
  INY
  LDA PCH
  STA (FWDREF_L),Y
  ; Advance pointer by 2
  CLC
  LDA FWDREF_L
  ADC #$02
  STA FWDREF_L
  LDA FWDREF_H
  ADC #$00
  STA FWDREF_H
  RTS
.too_many
  JMP err_too_many_forward_refs


; Check if current PC is in forward reference list (call in pass 2)
; On exit: C=1 if PC matches current list entry (use absolute mode)
;          C=0 if no match (use normal ZP detection)
;          If C=1, pointer is advanced to next entry
;          A, Y are not preserved
;          X is preserved
check_forward_ref
  LDY #$00
  LDA (FWDREF_L),Y
  CMP PCL
  BNE .no_match
  INY
  LDA (FWDREF_L),Y
  CMP PCH
  BNE .no_match
  ; Match - advance pointer and return C=1
  CLC
  LDA FWDREF_L
  ADC #$02
  STA FWDREF_L
  LDA FWDREF_H
  ADC #$00
  STA FWDREF_H
  SEC
  RTS
.no_match
  CLC
  RTS
