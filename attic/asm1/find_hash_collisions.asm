  JSR init_hash_tab
  JSR init_heap

  LDY# $00
  LDA# "A"
  STA,Y token
  INY
  LDA# "G"
  STA,Y token
  INY
  LDA# $00
  STA,Y token

  JSR calculate_hash
  LDAZ <hash
  TAY
  LDA# $01
  STA,Y hash_tab_l

loop
  LDY# $01
  LDA,Y token
  CMP# "Z"
  BEQ ~loop1
  CLC
  ADC# $01
  STA,Y token
  JMP loop2
loop1
  LDA# "A"
  STA,Y token
  LDY# $00
  LDA,Y token
  CMP# "Z"
  BEQ ~done
  CLC
  ADC# $01
  STA,Y token
loop2
  JSR calculate_hash
  LDAZ <hash
  TAY
  LDA,Y hash_tab_l
  BEQ ~loop
  ; Found
  LDY# $00
  LDA,Y token
  JSR write_b
  INY
  LDA,Y token
  JSR write_b
  LDA# " "
  JSR write_b
  JMP loop
done
  LDA# "\n"
  JSR write_b
  BRK $00

