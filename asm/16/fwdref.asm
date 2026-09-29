; Forward reference list management
; List is stored at FWDREF_LIST, terminated by $FFFF
; Each entry is 2 bytes (PC16) of an instruction with forward ref
;
; Requires:
;   FWDREF_LIST  - start address of forward reference list
;   FWDREF_LIMIT - max pointer value before adding (room for entry + terminator)
;   PC16         - zero page location containing program counter
;   err_too_many_forward_refs - error handler for list overflow

  .zeropage

FWDREF16:    .data $0000 ; Pointer to forward reference list

  .code


; Initialize forward reference list pointer (call at start of pass 1)
; Reset forward reference pointer (call at start of pass 2)
; On exit: A is not preserved
;          X, Y are preserved
init_fwdref_list:
reset_fwdref_ptr:
  SET16 FWDREF_LIST FWDREF16
  RTS


; Finalize forward reference list (call at end of pass 1)
; Writes $FFFF terminator at current pointer position
; On exit: A, Y are not preserved
;          X is preserved
finalize_fwdref_list:
  LDY #$00
  LDA #$FF
  STA (FWDREF16),Y
  INY
  STA (FWDREF16),Y
  RTS


; Add current PC to forward reference list (call in pass 1 when label not found)
; On exit: A, Y are not preserved
;          X is preserved
;          Jumps to err_too_many_forward_refs if list is full
add_forward_ref:
  ; Check if there's room (pointer must be < FWDREF_LIMIT - 2) to allow for terminator
  CMPI16 FWDREF16 FWDREF_LIMIT-$02
  BCS .too_many           ; >= FWDREF_LIMIT, no room for entry + terminator
  ; Store PC at current list position
  LDY #$00
  LDA PC16
  STA (FWDREF16),Y
  INY
  LDA PC16+$01
  STA (FWDREF16),Y
  ; Advance pointer by 2
  CLC
  ADCI16 FWDREF16 $02 FWDREF16
  RTS
.too_many:
  JMP err_too_many_forward_refs


; Check if current PC is in forward reference list (call in pass 2)
; On exit: C=1 if PC matches current list entry (use absolute mode)
;          C=0 if no match (use normal ZP detection)
;          If C=1, pointer is advanced to next entry
;          A, Y are not preserved
;          X is preserved
check_forward_ref:
  LDY #$00
  LDA (FWDREF16),Y
  CMP PC16
  BNE .no_match
  INY
  LDA (FWDREF16),Y
  CMP PC16+$01
  BNE .no_match
  ; Match - advance pointer and return C=1
  CLC
  ADCI16 FWDREF16 $02 FWDREF16
  SEC
  RTS
.no_match:
  CLC
  RTS
