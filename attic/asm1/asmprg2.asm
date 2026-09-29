write_b    = $F009


*          = $2000


start
  LDY# $00
loop
  LDA,Y message
  BEQ ~done
  JSR write_b
  INY
  JMP loop
done
  BRK $00 ; Success


message
  DATA "Hello, world!\n" $00


  DATA start
