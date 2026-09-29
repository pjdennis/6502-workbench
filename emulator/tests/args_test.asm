; Args test: outputs argc byte, then each argv string separated by newlines
* = $0400
  JMP main
  .include asm/17/environment.asm

PTR16 = $00       ; 16-bit pointer for string traversal

main:
  ; Output argc as raw byte
  JSR argc
  JSR write_b

  ; Loop through each argument
  STA $02           ; argc -> count remaining
  LDA #0
  STA $03           ; current arg index

.arg_loop:
  LDA $03
  CMP $02
  BEQ .done

  ; Get argv[index]
  LDA $03
  JSR argv          ; A = lo, X = hi
  STA PTR16
  STX PTR16+1

  ; Print the string
  LDY #0
.char_loop:
  LDA (PTR16),Y
  BEQ .next_arg     ; null terminator
  JSR write_b
  INY
  JMP .char_loop

.next_arg:
  LDA #$0A          ; newline separator
  JSR write_b
  INC $03
  JMP .arg_loop

.done:
  LDA #0
  JMP exit

  .byte <main, >main
