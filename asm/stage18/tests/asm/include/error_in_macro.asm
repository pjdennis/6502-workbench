; Include file that defines and invokes a macro with an error
  .macro HELPER
  LDA undefined
  .endmacro
  HELPER
