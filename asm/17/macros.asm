; Utility macros for 16-bit operations
;
; These macros assume consecutive zero-page locations for 16-bit values
; (low byte at ptr, high byte at ptr + 1)
;
; Requires: none (macro expansions only)


; INC16 ptr - Increment 16-bit value at ptr/ptr + 1
; Preserves A, X, Y
  .macro INC16 ptr
  INC ptr
  BNE .skip
  INC ptr + 1
.skip:
  .endmacro


; DEC16 ptr - Decrement 16-bit value at ptr/ptr + 1
; Preserves X, Y
  .macro DEC16 ptr
  LDA ptr
  BNE .skip
  DEC ptr + 1
.skip:
  DEC ptr
  .endmacro


; ADC16 ptr1 ptr2 ptr3 - Add two 16 bit values at ptr1 and ptr2, storing result at ptr3
; Clobbers A
  .macro ADC16 ptr1, ptr2, ptr3
  LDA ptr1
  ADC ptr2
  STA ptr3
  LDA ptr1 + 1
  ADC ptr2 + 1
  STA ptr3 + 1
  .endmacro


; ADCA16 ptr1 ptr2 - Adds A to value at ptr1, storing result at ptr2
; Clobbers A
  .macro ADCA16 ptr1, ptr2
  ADC ptr1
  STA ptr2
  LDA #0
  ADC ptr1 + 1
  STA ptr2 + 1
  .endmacro


; ADCI16 ptr1 val ptr2 - Adds val to value at ptr1, storing result at ptr2
; Clobbers A
  .macro ADCI16 ptr1, val, ptr2
  LDA ptr1
  ADC #<val
  STA ptr2
  LDA ptr1 + 1
  ADC #>val
  STA ptr2 + 1
  .endmacro


; SBC16 ptr1 ptr2 ptr3 - Subtracts the value at ptr2 from the value at ptr1, storing result at ptr3
; Clobbers A
  .macro SBC16 ptr1, ptr2, ptr3
  LDA ptr1
  SBC ptr2
  STA ptr3
  LDA ptr1 + 1
  SBC ptr2 + 1
  STA ptr3 + 1
  .endmacro


; SBCI16 ptr1 val ptr2 - subracts val from value at ptr1, storing result at ptr2
; Clobbers A
  .macro SBCI16 ptr1, val, ptr2
  LDA ptr1
  SBC #<val
  STA ptr2
  LDA ptr1 + 1
  SBC #>val
  STA ptr2 + 1
  .endmacro


; SBC16_8 ptr1 ptr2_8 ptr3 - Subracts 8 bit value at ptr2_8 from value at ptr1, storing result at ptr3
; Clobbers A
  .macro SBC16_8 ptr1, ptr2_8, ptr3
  LDA ptr1
  SBC ptr2_8
  STA ptr3
  LDA ptr1 + 1
  SBC #0
  STA ptr3 + 1
  .endmacro


; CMP16 ptr1 ptr2 Compares value at ptr1 to val at ptr2, setting flags accordingly
; After calling:
;   BEQ/BNE work for equality
;   BCC branches if value at ptr1 < value at ptr2
; Clobbers A
  .macro CMP16 ptr1, ptr2
  LDA ptr1 + 1
  CMP ptr2 + 1
  BNE .done
  LDA ptr1
  CMP ptr2
.done:
  .endmacro


; CMPI16 ptr val Compares val to value at ptr, setting flags accordingly
; After calling:
;   BEQ/BNE work for equality
;   BCC branches if value at ptr < val
; Clobbers A
  .macro CMPI16 ptr, val
  LDA ptr + 1
  CMP #>val
  BNE .done
  LDA ptr
  CMP #<val
.done:
  .endmacro


; TST16 ptr - Tests 16 bit value at ptr; use BEQ for zero, BNE for non zero
; Clobbers A
  .macro TST16 ptr
  LDA ptr
  ORA ptr + 1
  .endmacro


; ASL16 ptr - Shift 16 bit value at ptr left
  .macro ASL16 ptr
  ASL ptr
  ROL ptr + 1
  .endmacro


; LSR16 ptr - Shift 16 bit value at ptr right
  .macro LSR16 ptr
  LSR ptr + 1
  ROR ptr
  .endmacro


; ROL16 ptr - Rotate 16 bit value at ptr left
  .macro ROL16 ptr
  ROL ptr
  ROL ptr + 1
  .endmacro


; ROR16 ptr - Rotate 16 bit value at ptr right
  .macro ROR16 ptr
  ROR ptr + 1
  ROR ptr
  .endmacro


; CP16 src dst - Copy 16-bit value from src to dst
; Clobbers A
  .macro CP16 src, dst
  LDA src
  STA dst
  LDA src + 1
  STA dst + 1
  .endmacro


; SET16 val ptr - Load 16-bit immediate value into ptr/ptr + 1
; Clobbers A
  .macro SET16 val, ptr
  LDA #<val
  STA ptr
  LDA #>val
  STA ptr + 1
  .endmacro


; STA_LH16 ptr - Store A into the low and high bytes of ptr
; Most useful for A = $00 or A = $FF
; Preserves A, X, Y
  .macro STA_LH16 ptr
  STA ptr
  STA ptr + 1
  .endmacro


; PUSH16 ptr - Push the value at ptr to the stack
; Clobbers A
  .macro PUSH16 ptr
  LDA ptr
  PHA
  LDA ptr + 1
  PHA
  .endmacro


; POP16 ptr - Pops the value at ptr from the stack
; Clobbers A
  .macro POP16 ptr
  PLA
  STA ptr + 1
  PLA
  STA ptr
  .endmacro


; LDAX16 ptr - Load 16-bit value into A (low) / X (high)
; Used before calling subroutines that take A/X as 16-bit parameter
  .macro LDAX16 ptr
  LDA ptr
  LDX ptr + 1
  .endmacro


; STAX16 ptr - Store A (low) / X (high) into 16-bit pointer
  .macro STAX16 ptr
  STA ptr
  STX ptr + 1
  .endmacro
