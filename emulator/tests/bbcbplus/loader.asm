; bbcbplus test: the developer's way in. Run from disk (*LOADER), it loads
; the module image MODULE into a module holding RAM (--bbc-module-ram) in
; slot 4, bank by bank: select the bank, then OSGBPB reads 16 KB of the
; file into $8000-$BFFF, which writes the selected bank. Then it selects
; bank 0, puts the module's type from its header into the ROM type table
; ($02A1+4), as a sideways RAM loader does, and passes *HELLO to OSCLI.
; define:DIRECT16 selects banks as the direct16 scheme does (up to 16),
; define:CC128 as the Computer Concepts 128K carrier does (8).

osfind: = $FFCE
osgbpb: = $FFD1
oscli: = $FFF7
romcopy: = $F4
romsel: = $FE30
romtab: = $02A1
slot: = $04

blk: = $70
handle: = $7D
bank: = $7E

* = $1900
start:
  LDA #$40
  LDX #<name
  LDY #>name
  JSR osfind
  CMP #$00
  BNE .open
  BRK
  .byte 214
  .asciiz "File not found"
.open:
  STA handle
  LDA #slot
  STA romcopy
  STA romsel
  LDA #$00
  STA bank
.next:
  JSR select
  LDA handle
  STA blk
  LDA #$00
  STA blk+$01
  STA blk+$03
  STA blk+$04
  STA blk+$05
  STA blk+$07
  STA blk+$08
  LDA #$80
  STA blk+$02
  LDA #$40
  STA blk+$06
  LDA #$04
  LDX #blk
  LDY #$00
  JSR osgbpb
  BCS .last
  INC bank
  LDA bank
  .ifdef DIRECT16
  CMP #16
  .endif
  .ifdef CC128
  CMP #8
  .endif
  BNE .next
.last:
  LDA #$00
  LDY handle
  JSR osfind
  LDA #$00
  STA bank
  JSR select
  LDA $8006
  STA romtab+slot
  LDA #$0F
  STA romcopy
  STA romsel
  LDX #<command
  LDY #>command
  JMP oscli

; Select the bank in `bank`
select:
  .ifdef DIRECT16
  LDX bank
  LDA $BFF0,X
  .endif
  .ifdef CC128
  LDA $BFE0
  LDX bank
  LDA zone,X
  TAX
  LDA $BF00,X
  .endif
  RTS

zone:
  .byte $E0, $C0, $A0, $80, $60, $40, $20, $00
name:
  .byte "MODULE", $0D
command:
  .byte "HELLO", $0D
