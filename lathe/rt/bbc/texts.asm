; A part of the texts of the Lathe tools' errors in a module image (lathe/docs/bbc.md, "The texts
; in the module"): the code that writes one of its texts, then its tables. lathe/host/driver/
; bbcrom.py assembles this file with asm/pyasm.py once for each part, with the constants before
; it, `part_at` (where the part is, in the bank bbcrom.py puts it in, wherever there is room) and
; `claim` (the module's return from a service call, in the reserved bytes of every bank:
; lathe/rt/bbc/module.asm), and the part's tables after it (lathe/host/driver/msgpack.py: its
; texts, its own pairs). The texts of an image are in one part or more, each holding the texts
; from one number to another; the home bank's code (module.asm, "An error's text") finds the part
; of text Y, has written ": ", and enters the part's bank at text_part with Y the texts before
; it in the part.
;
; The texts are in text_texts in order, each its codes ended by a zero; a code is a character, or
; a pair of codes, which text_first and text_second give at the code plus $80 if that is below
; their length, each a character or a pair again. Everything here keeps to what module.asm
; keeps to: no read at $BFF0-$BFFF but to switch (the part ends by $BFEF, and an indexed read or
; a read through ($A8),Y that crosses a page makes its dummy read in the page below).

oswrch: = $FFEE
w0: = $A8                      ; the MOS's workspace for * commands, as module.asm uses it
w1: = $A9

* = part_at
text_part:
  LDA #<text_texts
  STA w0
  LDA #>text_texts
  STA w1
  TYA
  TAX                          ; the texts before it
  LDY #$00
  CPX #$00
  BEQ .write
.pass:
  LDA (w0),Y
  INY
  BNE .same
  INC w1
.same:
  CMP #$00
  BNE .pass                    ; to the end of this text
  DEX
  BNE .pass
.write:
  LDA (w0),Y
  BEQ .done
  JSR put_code
  INY
  BNE .write
  INC w1
  BNE .write                   ; always
.done:
  JMP claim                    ; the bank of entry again, and the call claimed

; One code: a character, or a pair, its first code and then its second (the 6502's stack holds
; the second while the first is written: three bytes a level, at most eight levels).
put_code:
  CLC
  ADC #$80
  CMP #text_second-text_first
  BCS .character
  TAX
  LDA text_second,X
  PHA
  LDA text_first,X
  JSR put_code
  PLA
  JMP put_code
.character:
  SBC #$80                     ; the carry is set: the code as it was
  JMP oswrch

; ---- the part's tables ----
