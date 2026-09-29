; test16.asm - Test program for new conventional syntax
; This file grows as we implement each addressing mode in asm16
;
; New syntax examples:
;   LDA #$42      ; immediate
;   LDA $12       ; zero page (value < $100)
;   LDA $1234     ; absolute
;   LDA $12,X     ; zero page indexed X
;   LDA $1234,X   ; absolute indexed X
;   LDA ($12),Y   ; indirect indexed Y
;   LDA ($12,X)   ; indirect indexed X
;   ASL A         ; accumulator

; === Define zero page variables first (for backward reference tests) ===
  .zeropage
zp_var1
  DATA $00             ; Zero page variable at known address
zp_var2
  DATA $00             ; Another ZP variable

  .code
* = $2000

; === Test backward reference to known zero page label ===
; Since the label is defined BEFORE use, the assembler knows it's < $100
; Current implementation: always uses absolute for labels (conservative)
  LDA zp_var1          ; Could be 2 bytes (A5 xx) but currently 3 bytes (AD xx xx)
  STA zp_var2          ; Could be 2 bytes (85 xx) but currently 3 bytes (8D xx xx)

; === Test implied mode instructions ===
start
  NOP
  CLC
  SEC
  TAX
  TXA
  TAY
  TYA
  INX
  INY
  DEX
  DEY
  PHA
  PLA
  RTS

; === Test immediate mode ===
  LDA #$42
  LDX #$55
  LDY #$AA
  ADC #$01
  SBC #$02
  AND #$0F
  ORA #$F0
  EOR #$FF
  CMP #$00
  CPX #$10
  CPY #$20

; === Test zero page mode ===
  LDA $10
  LDX $20
  LDY $30
  STA $40
  STX $50
  STY $60
  INC $70
  DEC $80
  BIT $90

; === Test absolute mode ===
  LDA $1234
  LDX $2345
  LDY $3456
  STA $4567
  STX $5678
  STY $6789
  INC $789A
  DEC $89AB
  BIT $9ABC
  JMP $ABCD
  JSR $BCDE

; === Test indexed modes ===
  ; Zero page indexed X
  LDA $10,X
  STA $20,X
  LDY $30,X
  STY $40,X

  ; Zero page indexed Y
  LDX $50,Y
  STX $60,Y

  ; Absolute indexed X
  LDA $1234,X
  STA $2345,X
  LDY $3456,X
  INC $4567,X
  DEC $5678,X

  ; Absolute indexed Y
  LDA $6789,Y
  STA $789A,Y
  LDX $89AB,Y

; === Test indirect modes ===
  ; Indirect indexed Y - ($zp),Y
  LDA ($10),Y
  STA ($20),Y
  ADC ($30),Y
  SBC ($40),Y
  AND ($50),Y
  ORA ($60),Y
  EOR ($70),Y
  CMP ($80),Y

  ; Indirect indexed X - ($zp,X)
  LDA ($12,X)
  STA ($34,X)
  ADC ($56,X)
  SBC ($78,X)

; === Test accumulator mode ===
  ASL A
  LSR A
  ROL A
  ROR A

; === Test branch instructions ===
  BCC branch_target
  BCS branch_target
  BEQ branch_target
  BNE branch_target
  BMI branch_target
  BPL branch_target
  BVC branch_target
  BVS branch_target

branch_target
  NOP

; === Test label starting with 'A' (must not be mistaken for accumulator mode) ===
ABSOLUTE
  JMP ABSOLUTE         ; Should use absolute mode, not accumulator!
  LDA #$AA

; === Test forward references ===
; Forward reference to label < $100 - must use absolute (3 bytes) on both passes
  LDA forward_zp       ; Must be 3 bytes (AD xx xx), not 2 bytes (A5 xx)
  STA forward_zp       ; Must be 3 bytes (8D xx xx), not 2 bytes (85 xx)
; Forward reference to label >= $100
  LDA forward_abs      ; Must be 3 bytes (AD xx xx)
  STA forward_abs      ; Must be 3 bytes (8D xx xx)

; Indirect modes with forward reference to ZP label
  LDA (forward_zp),Y   ; Forward ref to ZP - uses 1-byte operand on pass 1
  STA (forward_zp,X)   ; Forward ref to ZP - uses 1-byte operand on pass 1

  .zeropage
forward_zp
  DATA $00             ; Forward reference target in zero page

  .code
forward_abs
  NOP                  ; This label is at an address >= $100

; === Test indexed label addressing ===
; Note: This tests the bug mentioned in asm16.asm comments
  LDA forward_abs,X    ; Should be BD xx xx (absolute indexed X)
  STA forward_abs,Y    ; Should be 99 xx xx (absolute indexed Y)

; === Test JMP indirect ===
  JMP ($1234)          ; Should be 6C 34 12 (JMP indirect)
  JMP ($ABCD)          ; Should be 6C CD AB

; === Test label-based addressing modes ===
; These tests verify that labels work correctly in all addressing modes

; Immediate mode with label LSB/MSB operators
  LDA #<forward_abs    ; Low byte of label
  LDX #>forward_abs    ; High byte of label
  LDY #<zp_var1        ; Low byte of ZP label (should be small value)

; Indirect Y mode with ZP label (backward reference)
  LDA (zp_var1),Y      ; Should use value of zp_var1 as ZP address
  STA (zp_var2),Y

; Indirect X mode with ZP label (backward reference)
  LDA (zp_var1,X)
  STA (zp_var2,X)

; JMP indirect with backward reference label
jmp_vector
  DATA <jump_target >jump_target  ; Vector pointing to jump_target
jump_target
  NOP
  JMP (jmp_vector)     ; Should use address of jmp_vector (backward ref)

; === Test character literals in immediate mode (single quotes) ===
  LDA #'A'             ; Should be A9 41
  LDX #'Z'             ; Should be A2 5A
  LDY #'0'             ; Should be A0 30
  CMP #' '             ; Should be C9 20
  CPX #'!'             ; Should be E0 21

; === Test escape sequences ===
  LDA #'\n'            ; Should be A9 0A (linefeed)
  LDX #'\\'            ; Should be A2 5C (backslash)
  LDY #'\''            ; Should be A0 27 (single quote)
  ADC #'\"'            ; Should be 69 22 (double quote, optional escape)

; === Test constants in immediate mode ===
TEST_CONST = $42
TEST_MODE  = $02       ; Same value as MODE_IMM in asm16.asm
TEST_ADDR  = $1D00     ; Same value as TOKEN in asm16.asm
  LDA #TEST_CONST      ; Should be A9 42
  LDX #TEST_MODE       ; Should be A2 02

; === Test constants as memory operand ===
  LDA TEST_ADDR        ; Should be AD 00 1D
  STA TEST_ADDR        ; Should be 8D 00 1D

; Padding to make output visible
  DATA $00 $00
