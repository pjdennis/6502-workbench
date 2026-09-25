  .macro gd_send_word,address
  lda \address+1
  jsr gd_send_data
  lda \address
  jsr gd_send_data
  .endm


  .macro gd_send_word_immediate,value
  lda #>(\value)
  jsr gd_send_data
  lda #<(\value)
  jsr gd_send_data
  .endm


  .macro gd_send_command_immediate,value
  lda #\value
  jsr gd_send_command
  .endm


  .macro gd_send_data_immediate,value
  lda #\value
  jsr gd_send_data
  .endm


  .macro gd_send_x2,value
  lda #\value
; jsr gd_send_data
  sta PORTB
  lda #GD_E
  tsb GD_PORT
  trb GD_PORT
; lda <value>
; jsr gd_send_data
  tsb GD_PORT
  trb GD_PORT
  .endm
