; bbcbplus test: *COPY <from> <to> copies a file a byte at a time through
; OSFIND, OSBGET and OSBPUT. The names come from the command line tail
; (OSARGS 1). A missing <from> raises the error "File not found" (214),
; as a filing system would; the default BRKV handler prints it and the run
; ends with exit status 1. Loaded and entered at PAGE ($1900) by *RUN or
; *COPY (COPY.inf gives both addresses).

osfind: = $FFCE
osbget: = $FFD7
osbput: = $FFD4
osargs: = $FFDA

tail: = $70
src: = $74
dst: = $76
in: = $78
out: = $79

* = $1900
start:
  LDA #$01
  LDX #tail
  LDY #$00
  JSR osargs
  LDA tail
  STA src
  LDA tail+$01
  STA src+$01
  LDY #$00
.name:
  LDA (tail),Y
  CMP #$20
  BEQ .spaces
  CMP #$0D
  BEQ .usage
  INY
  BNE .name
.spaces:
  INY
  LDA (tail),Y
  CMP #$20
  BEQ .spaces
  CMP #$0D
  BEQ .usage
  TYA
  CLC
  ADC tail
  STA dst
  LDA tail+$01
  ADC #$00
  STA dst+$01
  LDA #$40
  LDX src
  LDY src+$01
  JSR osfind
  CMP #$00
  BEQ .notfound
  STA in
  LDA #$80
  LDX dst
  LDY dst+$01
  JSR osfind
  STA out
.copy:
  LDY in
  JSR osbget
  BCS .end
  LDY out
  JSR osbput
  JMP .copy
.end:
  LDA #$00
  LDY #$00
  JSR osfind
  RTS
.notfound:
  BRK
  .byte 214
  .asciiz "File not found"
.usage:
  BRK
  .byte 220
  .asciiz "Syntax: COPY <from> <to>"
