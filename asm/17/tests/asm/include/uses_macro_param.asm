; Include file invoked from inside a macro body. References the
; macro's parameter `x`. asm17's parameter scoping is source-type-
; agnostic: the macro's EXPANSION_ID scope stays active while we read
; from this file, so `x` resolves to whatever the macro was called
; with. Used by macro_param_visible_in_include.
  LDA #x
