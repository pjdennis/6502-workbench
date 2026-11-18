; The code of a Lathe module image for the BBC Model B+128 (lathe/docs/bbc.md, "Step 3, as built:
; the ROM form", and "The 128 KB module"): sixteen 16 KB banks behind one sideways slot, scheme
; direct16 (a read of $BFF0+n latches bank n, from any bank), or eight, scheme direct8 (the same
; for n 0 to 7, $BFF8-$BFFF their mirror). lathe/host/driver/bbcrom.py assembles this file with
; asm/pyasm.py, with two constants before it, `home` (the bank that holds the module's own code
; and tables, the home bank) and `home_at` (their address there), and its own tables (the command
; table, the copy lists, the *HELP text, then the texts of the errors, lathe/host/driver/
; msgpack.py's) after the line `; ---- the tables ----` at the end, and
; puts the reserved bytes in every bank. Written for the repository's own assembler: upper-case
; mnemonics, constants before their use. bbcrom.py also gives `entry_rest`, the bytes of a command's
; entry in the table after its name's zero (5, or 7 with the check below), and `check_himem` when
; the image checks HIMEM.
;
; Every bank begins with the same RESERVED bytes, $8000-$804F: the sideways ROM header, the
; service code and the bank's own number at $804F (the one byte that differs), so that the MOS
; finds a valid ROM whichever bank the latch holds: it powers up undefined, a reset can come while
; any bank is selected, and the MOS issues service calls while a tool runs in any bank. A Lathe
; program's banks are linked with the window $8050-$BFDF (lathe/env/bbc-rom.env).
;
; The service code answers only service calls 4 (an unknown * command), 9 (*HELP) and $4C, the
; module's own (a tool's ROM form asks for the text of an error: "An error's text", below; the
; reserved bytes have one byte to spare). For any other it returns at once with A, X and Y as
; they were (only the flags change). For 4, 9 and $4C it pushes the call and this bank's number, selects the home bank by a read of $BFF0+home, an
; instruction of the reserved bytes, so that the next one, the same in the home bank, goes on
; there; and the home bank returns through `back` or `claim`, which select the bank of entry
; again in the same way and return from the service call: unclaimed with A, X (the slot, from
; $F4) and Y as given, or claimed with A = 0.
;
; The home bank holds, at home_at (after its program's code, if a program has code in it; bank 0
; and $8050 in the sixteen-bank image), the code below and the tables, and after them the packed
; texts of the compiler's and the linker's errors, in every image; the programs' resident
; parts and their regions' constants are in the ends of the banks, in pieces, wherever there is
; room. For a command of its table it:
;
;   0. with check_himem (bbcrom.image(check_himem=True), every image bbcrom.py makes by default:
;      lathe/docs/bbc.md, "Started in another screen mode"), refuses the command if HIMEM (OSBYTE 132) is below the top of the
;      program's memory, the word after its entry's start address: the screen of the mode would be
;      in its tables, and the MOS's text would write over them. The error, `Mode 7 needed`, is
;      copied to $0100 and raised there, as a sideways ROM's errors must be (the language that
;      prints it is in the window then), before anything is copied or written;
;   1. copies the command's tail, after the spaces, from ($F2),Y to $0700, ended by CR (at most
;      239 bytes; from the end down when the line is below $0700, so that it may overlap);
;   2. writes the stub, 16 bytes at $07F0-$07FF, with the program's start address and the slot
;      the MOS selected for the service call ($F4), which the program reads at $07F4
;      (lathe/rt/bbc.lth, ROM_SLOT):
;          $07F0  JSR start          the program; it returns here with status 0
;          $07F3  LDA #slot
;          $07F5  STA $F4
;          $07F7  STA $FE30          the module's slot again
;          $07FA  LDA $BFF0+home     and the home bank
;          $07FD  JMP ended
;   3. copies the copier (below) to $0400 and runs it for each entry of the command's copy list:
;      each piece of the program's resident part (its fixed code and constants) from the banks of
;      the image to its place in main RAM, and each piece of the constants of its regions to
;      their sideways RAM slots, a byte at a time, selecting the source bank and the destination
;      slot for each;
;   4. jumps to the stub.
;
; Why there: $0400-$07FF is the language's workspace and $00-$8F its zero page; once a command of
; the module has been matched the language that was running cannot go on (the tool takes its
; zero page, its workspace and the memory from PAGE), so the module may use both. The copier at
; $0400 is needed only before the program starts, and the program's variables may lie over it
; (`more data $0401 $06FF`). The tail and the stub must last while the program runs: a program
; of the ROM form leaves $0700-$07FF out of its data, as one run with *RUN leaves the command
; line there (lathe/env/bbc-rom.env; bbcrom.py checks it). $A8-$AF are the MOS's workspace for
; * commands, and $8C-$8E of the language's zero page hold the walk of the copy list.
;
; The end. The program returns to $07F3 (status 0; exit(0) from any depth too, with the stack
; pointer its start-up code kept at $0400), which selects the module and the home bank and jumps
; to `ended`: if the current language (OSBYTE 252) is a language ROM (its type, from the table
; OSBYTE 170 gives, has bit 6), it is entered again with OSBYTE 142, which does not return, as a
; tool that has used the language's memory must; otherwise the service call returns claimed. An
; error, exit(N) with N not 0 among them, never comes back here: the MOS's BRK handler goes to the
; language's error handler.
;
; Everything here keeps to what a real NMOS 6502 does: no instruction ends within a byte of the
; switching addresses (the code and tables end by $BFDF), no data is read at $BFF0-$BFFF but to
; switch, and every indexed access to a switching address ($BFF0,X) stays in its page, so that no
; dummy read latches a bank. The copier reads its sources with LDA (zp),Y and Y = 0, which makes
; no dummy read, so pieces may run to $BFEF.

romcopy: = $F4
cli_ptr: = $F2
romsel: = $FE30
latch: = $BFF0
osasci: = $FFE3
oswrch: = $FFEE
text_call: = $4C               ; the service call that asks for an error's text
osbyte: = $FFF4
tail: = $0700
stub_ram: = $07F0
stub_slot: = $07F4
copier_ram: = $0400
w0: = $A8
w1: = $A9
w2: = $AA
w3: = $AB
w4: = $AC
w5: = $AD
w6: = $AE
w7: = $AF
list: = $8C
count: = $8E

; ---- every bank: the header and the service code ----
* = $8000
header:
  .byte $00, $00, $00          ; no language entry
  JMP service                  ; the service entry
  .byte $82                    ; type: a service entry, 6502 code
  .byte copyright-header       ; the copyright string's offset
  .byte $01                    ; version
  .byte "Lathe"                ; title
copyright:
  .byte $00
  .byte "(C) 6502-workbench"
  .byte $00

service:
  CMP #$04
  BEQ .ours
  CMP #$09
  BEQ .ours
  CMP #text_call
  BEQ .ours
  RTS
.ours:
  PHA                          ; the call
  LDA number
  PHA                          ; the bank it came in
  LDA latch+home               ; the home bank: the next instruction is its, the same
  JMP bank0

; Return from the service call, unclaimed: the stack holds the bank of entry and then the call;
; Y is as given.
back:
  PLA
  TAX
  LDA latch,X                  ; the bank of entry: the rest is its, the same
  PLA
  LDX romcopy
  RTS

; Return from the service call, claimed (A = 0).
claim:
  PLA
  TAX
  LDA latch,X
  PLA
  LDA #$00
  LDX romcopy
  RTS

* = $804F
number:
  .byte $00                    ; the bank's own number: bbcrom.py writes it in each bank
reserved_end:

; ---- the home bank ----
* = home_at
; From the service code: A and X as they come, Y the argument, the stack the bank of entry and
; the call.
bank0:
  TSX
  LDA $0102,X                  ; the call
  CMP #text_call
  BNE .not_text
  JMP text
.not_text:
  CMP #$09
  BNE .command
  JMP help
.command:
  STY w0                       ; where the command starts
  LDX #$00
.next:
  LDA commands,X
  BEQ .none                    ; the end of the table
  LDY w0
.compare:
  LDA (cli_ptr),Y
  CMP #$61
  BCC .upper
  AND #$DF                     ; a lower-case letter
.upper:
  CMP commands,X
  BNE .skip
  INY
  INX
  LDA commands,X
  BNE .compare
  LDA (cli_ptr),Y              ; the name has ended: the command word must end here too
  CMP #$20
  BEQ .found
  CMP #$0D
  BEQ .found
  BNE .after
.skip:
  INX
  LDA commands,X
  BNE .skip
.after:
  TXA                          ; X at the name's zero: its list and start follow
  CLC
  ADC #entry_rest
  TAX
  JMP .next
.none:
  LDY w0
  JMP back
.found:
  .ifdef check_himem
  STY w2                       ; where the tail starts in the line
  STX w3                       ; the entry
  LDA #$84                     ; OSBYTE 132: HIMEM, in X and Y
  JSR osbyte
  STX w0
  STY w1
  LDX w3
  LDA w0                       ; HIMEM less the top of the program's memory
  CMP commands+5,X
  LDA w1
  SBC commands+6,X
  BCS .room
  LDX #too_low_end-too_low-$01 ; below: the error, from $0100
.error:
  LDA too_low,X
  STA $0100,X
  DEX
  BPL .error
  JMP $0100
.room:
  LDY w2
  .endif
  LDA commands+1,X
  STA w4                       ; the copy list
  LDA commands+2,X
  STA w5
  LDA commands+3,X
  STA w6                       ; the start address
  LDA commands+4,X
  STA w7
.spaces:
  LDA (cli_ptr),Y
  CMP #$20
  BNE .tail
  INY
  BNE .spaces
.tail:
  TYA                          ; the tail's address
  CLC
  ADC cli_ptr
  STA w0
  LDA cli_ptr+$01
  ADC #$00
  STA w1
  LDY #$00
.length:
  LDA (w0),Y
  CMP #$0D
  BEQ .counted
  INY
  CPY #239
  BNE .length
.counted:
  STY w2                       ; its length, without the CR
  LDA w1
  CMP #>tail
  BCC .down
  LDY #$00                     ; at or above $0700: from the start up
.up:
  CPY w2
  BEQ .cr
  LDA (w0),Y
  STA tail,Y
  INY
  BNE .up
.down:
  LDY w2                       ; below $0700: from the end down
  BEQ .cr
.dloop:
  DEY
  LDA (w0),Y
  STA tail,Y
  CPY #$00
  BNE .dloop
.cr:
  LDY w2
  LDA #$0D
  STA tail,Y
  LDX #$0F                     ; the stub
.stub:
  LDA stub,X
  STA stub_ram,X
  DEX
  BPL .stub
  LDA w6
  STA stub_ram+$01
  LDA w7
  STA stub_ram+$02
  LDA romcopy
  STA stub_slot
  LDX #copier_end-copier-$01   ; the copier
.copy:
  LDA copier,X
  STA copier_ram,X
  DEX
  BPL .copy
  LDA w4                       ; the copy list: a count, then entries of 8 bytes
  STA list
  LDA w5
  STA list+$01
  LDY #$00
  LDA (list),Y
  STA count
  INC list
  BNE .entry
  INC list+$01
.entry:
  LDA count
  BEQ .go
  LDY #$07
.fetch:
  LDA (list),Y
  STA $00A8,Y
  DEY
  BPL .fetch
  JSR copier_ram
  LDA list
  CLC
  ADC #$08
  STA list
  BCC .counted_down
  INC list+$01
.counted_down:
  DEC count
  JMP .entry
.go:
  JMP stub_ram

; The program has returned: the module and the home bank are selected. Enter the current language
; again if it is a language ROM; otherwise return from the service call, claimed.
ended:
  LDA #$FC                     ; OSBYTE 252: the current language, in X
  LDX #$00
  LDY #$FF
  JSR osbyte
  STX w0
  LDA #$AA                     ; OSBYTE 170: the ROM type table's address, in X and Y
  LDX #$00
  LDY #$FF
  JSR osbyte
  STX w2
  STY w3
  LDY w0
  LDA (w2),Y
  AND #$40
  BEQ .none
  LDX w0
  LDA #$8E                     ; OSBYTE 142: does not return
  JSR osbyte
.none:
  JMP claim

; *HELP: with no argument, the module's lines; with one, nothing. Never claimed.
help:
  STY w0
.spaces:
  LDA (cli_ptr),Y              ; spaces are no argument
  CMP #$20
  BNE .argument
  INY
  BNE .spaces
.argument:
  CMP #$0D
  BNE .quiet
  LDX #$00
.print:
  LDA help_text,X
  BEQ .done
  JSR osasci
  INX
  BNE .print
.done:
.quiet:
  LDY w0
  JMP back

  .ifdef check_himem
; The error when HIMEM is below the program's memory: BRK, its number, its text, 0.
too_low:
  .byte $00, $00
  .asciiz "Mode 7 needed"
too_low_end:
  .endif

; An error's text: a tool's ROM form asks for text Y with OSBYTE 143, X = text_call (lathe/rt/
; bbc.lth, error_text), and the module writes ": " and the text with OSWRCH and claims the call;
; when no ROM claims it, nothing is written, and the error is its number alone. Text n is the
; compiler's error n, text 255 - n the linker's. The texts (lathe/host/driver/msgpack.py packs
; them from the host's tables; bbcrom.py puts them after the tables below) are in text_texts in
; order from 0, each its codes ended by a zero; a code is a character, or a pair of codes, which
; text_first and text_second give at the code plus $80 if that is below their length.
text:
  LDA #$3A                     ; ": "
  JSR oswrch
  LDA #$20
  JSR oswrch
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
  JMP claim

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

; The stub, copied to $07F0 (above).
stub:
  .byte $20, $00, $00          ; JSR start
  .byte $A9, $00               ; LDA #slot
  .byte $85, romcopy           ; STA $F4
  .byte $8D                    ; STA $FE30
  .word romsel
  .byte $AD                    ; LDA $BFF0+home
  .word latch+home
  .byte $4C                    ; JMP ended
  .word ended

; The copier, copied to $0400 and run there, where switching the module's bank does not pull
; the code from under the CPU (so it uses no address of its own: only relative branches).
; $A8/$A9 the source, $AA/$AB the destination, $AC/$AD the count (not 0), $AE the source's
; bank, $AF the destination: $FF main RAM, else a sideways RAM slot. The home bank again at the
; end.
copier:
  LDY #$00
.loop:
  LDX w6
  LDA latch,X                  ; the source's bank
  LDA (w0),Y
  LDX w7
  BMI .main
  STX romcopy                  ; a sideways RAM slot
  STX romsel
  STA (w2),Y
  LDX stub_slot                ; the module again
  STX romcopy
  STX romsel
  BPL .next                    ; a slot, 0 to 15: always
.main:
  STA (w2),Y
.next:
  INC w0
  BNE .source
  INC w1
.source:
  INC w2
  BNE .dest
  INC w3
.dest:
  LDA w4
  BNE .low
  DEC w5
.low:
  DEC w4
  LDA w4
  ORA w5
  BNE .loop
  LDA latch+home
  RTS
copier_end:

; ---- the tables ----
