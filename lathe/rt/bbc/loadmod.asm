; LOADMOD: the developer's loader of a Lathe module image (lathe/docs/bbc.md, "Step 3, as built:
; the ROM form"), run from disk on a BBC Model B+128 whose module is the developer's form, RAM:
;
;     *RUN LOADMOD IMAGE [SLOT]
;
; reads the image file IMAGE (lathe/host/driver/bbcrom.py) into the module in slot SLOT (4 if not
; given) bank by bank, and enters the module's type in the MOS's ROM type table, so that the MOS
; offers it service calls from then on, without a reset. After it the module's * commands work
; as from the ROM. The file holds the sixteen banks (262,144 bytes), or banks 0 to N only
; (bbcrom.py --short: the banks in use, which fit a disc's side where the whole image does not);
; each bank after the file's last gets the reserved bytes alone, $8000-$804F as the last bank
; read has them with its own number at $804F, so that every bank still holds the header and
; service code whichever bank the latch is at, and the rest of it is left as it was. A file that
; ends inside a bank, or is empty, is not a module image. lathe/host/driver/bbcrom.py assembles it with
; asm/pyasm.py (bbcrom.loader(), or its --loader option) into LOADMOD and LOADMOD.inf, loaded and
; entered at $1900.
;
; A bank is read with OSGBPB into main RAM, $2000-$5FFF, and only then copied into the module
; with its slot selected: on a real machine the filing system is itself a sideways ROM, in the
; window while it runs, so it cannot write the module there. The last 32 bytes of a bank are not
; copied: the image has nothing there ($BFE0-$BFFF hold the switching addresses, and a write
; there, through STA (zp),Y, makes a dummy read of its address first on an NMOS 6502). $F4 and
; ROMSEL are put back as they were before each MOS call.

osfind: = $FFCE
osgbpb: = $FFD1
osargs: = $FFDA
osbyte: = $FFF4
romcopy: = $F4
romsel: = $FE30
latch: = $BFF0

tailp: = $70
src: = $72
dst: = $74
table: = $76
handle: = $78
slot: = $79
bank: = $7A
entry: = $7B
rest: = $7C                    ; 0 while the file has banks; then not 0
blk: = $80
buffer: = $2000

* = $1900
start:
  LDA #$01                     ; the tail: OSARGS 1
  LDX #tailp
  LDY #$00
  JSR osargs
  LDY #$00
  JSR spaces
  LDX #$00
.name:
  LDA (tailp),Y
  CMP #$20
  BEQ .named
  CMP #$0D
  BEQ .named
  STA name,X
  INY
  INX
  CPX #$40
  BNE .name
.named:
  CPX #$00
  BNE .some
  JMP no_name
.some:
  LDA #$0D
  STA name,X
  JSR spaces
  LDA #$04                     ; the slot, 4 if none is given
  STA slot
  LDA (tailp),Y
  CMP #$0D
  BEQ .open
  LDA #$00
  STA slot
.digit:
  LDA (tailp),Y
  CMP #$30
  BCC .number
  CMP #$3A
  BCS .number
  AND #$0F
  PHA
  LDA slot                     ; slot = slot * 10 + digit
  ASL
  ASL
  CLC
  ADC slot
  ASL
  STA slot
  PLA
  CLC
  ADC slot
  STA slot
  INY
  CMP #$10
  BCC .digit
  JMP bad_slot
.number:
  CMP #$20
  BEQ .open
  CMP #$0D
  BEQ .open
  JMP bad_slot
.open:
  LDA #$40
  LDX #<name
  LDY #>name
  JSR osfind
  CMP #$00
  BNE .opened
  JMP not_found
.opened:
  STA handle
  LDA romcopy
  STA entry
  LDA #$00
  STA bank
  STA rest
.bank:
  LDA rest
  BNE .full
  LDA handle                   ; OSGBPB 4: 16 KB to the buffer
  STA blk
  LDA #<buffer
  STA blk+$01
  LDA #>buffer
  STA blk+$02
  LDA #$00
  STA blk+$03
  STA blk+$04
  STA blk+$05
  STA blk+$07
  STA blk+$08
  LDA #$40
  STA blk+$06
  LDA #$04
  LDX #blk
  LDY #$00
  JSR osgbpb
  BCC .full
  LDA blk+$05                  ; nothing read, past bank 0: the file ends here
  ORA blk+$07
  ORA blk+$08
  BNE .short
  LDA blk+$06
  CMP #$40
  BNE .short
  LDA bank
  STA rest
  BNE .full
.short:
  JMP short
.full:
  LDA slot                     ; the module, and the bank
  STA romcopy
  STA romsel
  LDX bank
  LDA latch,X
  LDA rest
  BEQ .copy
  LDY #$00                     ; past the file: the reserved bytes alone
.head:
  LDA buffer,Y
  STA $8000,Y
  INY
  CPY #$4F
  BNE .head
  STX $804F                    ; the bank's own number
  JMP .copied
.copy:
  LDA #<buffer
  STA src
  LDA #>buffer
  STA src+$01
  LDA #$00
  STA dst
  LDA #$80
  STA dst+$01
  LDY #$00
.page:
  LDA (src),Y
  STA (dst),Y
  INY
  BNE .page
  INC src+$01
  INC dst+$01
  LDA dst+$01
  CMP #$BF
  BNE .page
.last:
  LDA (src),Y                  ; $BF00-$BFDF
  STA (dst),Y
  INY
  CPY #$E0
  BNE .last
.copied:
  LDA entry
  STA romcopy
  STA romsel
  INC bank
  LDA bank
  CMP #$10
  BEQ .loaded
  JMP .bank
.loaded:
  LDA #$00                     ; close it
  LDY handle
  JSR osfind
  LDA #$AA                     ; OSBYTE 170: the ROM type table
  LDX #$00
  LDY #$FF
  JSR osbyte
  STX table
  STY table+$01
  LDA slot                     ; bank 0's type, at $8006, into the table
  STA romcopy
  STA romsel
  LDA latch
  LDX $8006
  LDA entry
  STA romcopy
  STA romsel
  TXA
  LDY slot
  STA (table),Y
  RTS

; Skip the spaces at (tailp),Y.
spaces:
  LDA (tailp),Y
  CMP #$20
  BNE .end
  INY
  BNE spaces
.end:
  RTS

no_name:
  BRK
  .byte 220
  .asciiz "Syntax: LOADMOD IMAGE [SLOT]"
bad_slot:
  BRK
  .byte 220
  .asciiz "Bad slot"
not_found:
  BRK
  .byte 214
  .asciiz "File not found"
short:
  LDA #$00                     ; close it
  LDY handle
  JSR osfind
  BRK
  .byte 220
  .asciiz "Not a module image (too short)"

name:
  .byte $00
