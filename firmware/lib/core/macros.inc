; A selection of generic macros

  .macro inc16,address
  inc \address
  bne .\@
  inc \address+1
  .\@:
  .endm


  .macro dec16usingA,address
  lda \address
  bne .\@
  dec \address+1
.\@:
  dec \address
  .endm


  .macro add8iTo16usingA,address,value
  clc
  lda \address
  adc #\value
  sta \address
  bcc .\@
  inc \address+1
.\@:
  .endm


  .macro add16iTo16usingA,address,value
  clc
  lda \address
  adc #<(\value)
  sta \address
  lda \address+1
  adc #>(\value)
  sta \address+1
  .endm


  .macro copy16usingA,destination,source
  lda \source
  sta \destination
  lda \source+1
  sta \destination+1
  .endm


  .macro stz16,address
  stz \address
  stz \address+1
  .endm


  .macro sti16usingA,address,value
  lda #<(\value)
  sta \address
  lda #>(\value)
  sta \address+1
  .endm


  .macro push16usingA,address
  lda \address+1
  pha
  lda \address
  pha
  .endm


  .macro pop16usingA,address
  pla
  sta \address
  pla
  sta \address+1
  .endm


  .macro ldaxi,value
  lda #<(\value)
  ldx #>(\value)
  .endm
