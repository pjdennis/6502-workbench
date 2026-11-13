; Include file invoked from inside a macro body. References `y`,
; which is the OUTER macro's parameter (the macro that invoked the
; one we're inside of). asm17's parameter lookup stops at the
; innermost macro's scope -- it does NOT walk up to outer macros --
; so `y` is not visible here. Used by
; macro_outer_param_not_visible_via_include to pin that down.
  LDA #y
