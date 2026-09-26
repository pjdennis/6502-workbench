; Editor-local macros (the shared 16-bit macros are in 17/macros.asm,
; which the assembler also uses, so editor-only macros live here)

; ADDA16 ptr - Add A (unsigned) to the 16-bit value at ptr/ptr + 1
; 9 bytes, where CLC + ADCA16 ptr, ptr takes 11
; Clobbers A (= new low byte); carry undefined afterwards
  .macro ADDA16 ptr
  CLC
  ADC ptr
  STA ptr
  BCC .skip
  INC ptr + 1
.skip:
  .endmacro

; PRINT_STR addr - Print null-terminated string at addr
; Clobbers A, X, Y, STR_PTR16
  .macro PRINT_STR addr
  LDA #<addr
  LDX #>addr
  JSR write_string_ax
  .endmacro

; PRINT_TEXT addr - The same through text_putc (print_string_ax)
  .macro PRINT_TEXT addr
  LDA #<addr
  LDX #>addr
  JSR print_string_ax
  .endmacro
