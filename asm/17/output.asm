; output.asm - PC management and byte emission
;
; Provides: emit, update_pc, advance_pc_to_hex16
;
; Requires:
;   HEX16, PC16, PASS, IN_ZEROPAGE, STARTED (asm.asm)
;   write (environment.asm)
;   INC16, CMP16, CP16 (macros.asm)
;   err_zeropage_overflow, err_cannot_move_pc_backwards (errors.asm)

  .code


; Emit value (pass 2 only) and increment PC
; On entry A contains the byte to emit
;          X contains the file handle to write to
; On exit A, X, Y are preserved
; TODO: Consolidate the PASS and IN_ZEROPAGE flags so that emit can
;       do a single check instead of two for suppression of output
emit:
  BIT IN_ZEROPAGE
  BMI .in_zeropage     ; If in zero page, handle separately
  ; Not in zero page - proceed with normal emit logic
  INC16 PC16
  BIT PASS
  BPL .skip            ; Skip writing during pass 1
  JMP write            ; Tail call
.skip:
  RTS
.in_zeropage:
  ; In zero page - check for overflow BEFORE incrementing
  ; If high byte already non-zero, we've already overflowed past $FF
  LDA PC16 + 1
  BNE .overflow
  INC16 PC16           ; Safe to increment
  RTS                  ; No writing in zeropage
.overflow:
  JMP err_zeropage_overflow


; Fast forward the program counter
; On entry PC16 contains the current program counter
;          HEX16 contains the new PC value
; On exit
; Raises 'Cannot move PC backwards' error if attempting to move PC backwards
update_pc:
  BIT IN_ZEROPAGE
  BMI .no_fill         ; No fill or STARTED check in zeropage
  BIT STARTED
  BMI .started
  DEC STARTED
  BNE .no_fill         ; Always taken
.started:
  CMP16 HEX16, PC16
  BCC .less            ; HEX16 < PC16: error
  JMP advance_pc_to_hex16
.less:
  JMP err_cannot_move_pc_backwards
.no_fill:
  CP16 HEX16, PC16
  RTS


; Advance PC16 to the value in HEX16
; In .zeropage: sets PC, checks overflow
; In .code pass 1: just sets PC (no output)
; In .code pass 2: emits zero-fill bytes
; Caller must ensure HEX16 >= PC16
advance_pc_to_hex16:
  BIT IN_ZEROPAGE
  BMI .zp
  BIT PASS
  BPL .just_set        ; pass 1: just set PC
.loop:
  CMP16 HEX16, PC16
  BEQ .done
  LDA #$00
  JSR write
  INC16 PC16
  BNE .loop            ; Always taken
.done:
  RTS
.just_set:
  CP16 HEX16, PC16
  RTS
.zp:
  LDA HEX16 + 1
  BNE .zp_overflow     ; Target > $FF
  CP16 HEX16, PC16
  RTS
.zp_overflow:
  JMP err_zeropage_overflow
