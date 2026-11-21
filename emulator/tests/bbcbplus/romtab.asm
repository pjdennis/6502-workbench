; bbcbplus test: print the machine as a program sees it, then return. One line: OSBYTE 0's
; machine (X=1), PAGE's high byte (OSBYTE 131) as two hex digits, a space, and a character for
; each slot 0 to 15 from the ROM type table (OSBYTE 170): `.` for none, `L` for a language, `S`
; for a service ROM. Loaded at $1900.

oswrch: = $FFEE
osnewl: = $FFE7
osbyte: = $FFF4
table: = $70

* = $1900
start:
  LDA #$00                     ; OSBYTE 0, X=1: the machine
  LDX #$01
  JSR osbyte
  TXA
  JSR hex_digit
  LDA #$83                     ; OSBYTE 131: PAGE, its high byte
  JSR osbyte
  TYA
  LSR
  LSR
  LSR
  LSR
  JSR hex_digit
  TYA
  AND #$0F
  JSR hex_digit
  LDA #$20
  JSR oswrch
  LDA #$AA                     ; OSBYTE 170: the table's address
  LDX #$00
  LDY #$FF
  JSR osbyte
  STX table
  STY table+1
  LDY #$00
.slot:
  LDA (table),Y
  BEQ .none
  AND #$40
  BEQ .service
  LDA #$4C
  BNE .put
.service:
  LDA #$53
  BNE .put
.none:
  LDA #$2E
.put:
  JSR oswrch
  INY
  CPY #$10
  BNE .slot
  JSR osnewl
  RTS

hex_digit:                     ; A (0-15) as a hex digit
  CMP #$0A
  BCC .digit
  ADC #$06
.digit:
  ADC #$30
  JMP oswrch
