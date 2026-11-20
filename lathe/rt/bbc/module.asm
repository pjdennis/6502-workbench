; The code of a Lathe module image for the BBC Model B+128 (lathe/docs/bbc.md, "Step 3, as built:
; the ROM form", and "The 128 KB module"): sixteen 16 KB banks behind one sideways slot, scheme
; direct16 (a read of $BFF0+n latches bank n, from any bank), or eight, scheme direct8 (the same
; for n 0 to 7, $BFF8-$BFFF their mirror). lathe/host/driver/bbcrom.py assembles this file with
; asm/pyasm.py, with two constants before it, `home` (the bank that holds the module's own code
; and tables, the home bank) and `home_at` (their address there), and its own tables (the command
; table, the copy lists, the *HELP text, then the table of the parts of the texts of the errors,
; "An error's text" below) after the line `; ---- the tables ----` at the end, and
; puts the reserved bytes in every bank. Written for the repository's own assembler: upper-case
; mnemonics, constants before their use. bbcrom.py also gives `entry_rest`, the bytes of a command's
; entry in the table after its name's zero (5, or 7 with the check below), and `check_himem` when
; the image checks HIMEM (and PAGE), and `placer` when a program of it has dynamic regions (the
; shared placer, `place` below).
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
; and $8050 in the sixteen-bank image), the code below and the tables; the parts of the packed
; texts of the compiler's and the linker's errors (lathe/rt/bbc/texts.asm), in every image, are in
; this bank or others, wherever there is room, and the programs' resident
; parts and their regions' constants are in the ends of the banks, in pieces, wherever there is
; room. For a command of its table it:
;
;   0. with check_himem (bbcrom.image(check_himem=True), every image bbcrom.py makes by default:
;      lathe/docs/bbc.md, "Started in another screen mode"), refuses the command if HIMEM (OSBYTE 132) is below the top of the
;      program's memory, the word after its entry's start address: the screen of the mode would be
;      in its tables, and the MOS's text would write over them. The error, `Mode 7 needed`, is
;      copied to $0100 and raised there, as a sideways ROM's errors must be (the language that
;      prints it is in the window then), before anything is copied or written; and, the same
;      way, `PAGE too high` if PAGE (OSBYTE 131) is above the program's start address, where its
;      resident part is copied to, which would be over the filing system's workspace;
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
place_text: = $FF              ; text 255 (the linker's error 0, which is none): place a tool's regions
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
; The placer's variables (`place`, below), at the bottom of the stack's page.
p_code_lo: = $0100
p_top: = $0102
p_page: = $0104
p_himem: = $0106
p_before: = $0108
p_linked: = $010A
p_goes: = $010C
p_end: = $010E
p_areas: = $0110               ; the free areas: main RAM's, then the free sideways RAM's
p_max_areas: = $0C
p_first_lo: = $0111            ; each area's first byte not given out, and its last
p_first_hi: = $011D
p_last_lo: = $0129
p_last_hi: = $0135
p_slot: = $0141                ; its slot, or $FF in main RAM
p_regions: = $014D
p_pages: = $014E
p_number: = $014F
p_value: = $0151               ; the region's bank's value as linked
p_new: = $0152                 ; and the one it gets
p_room: = $0153                ; the address of its capacity variable, or 0
p_offset: = $0155              ; with one: where its last variable starts in its block
p_grant: = $0157               ; the bytes an area gives it, for p_take_most
p_best: = $0159                ; the area chosen so far (p_pick), and the bytes it gives
p_most: = $015A
p_least: = $015C               ; with a capacity: the least bytes of its block, and the most
p_ceiling: = $015E             ; (0: no limit)
p_kind: = $0160                ; which areas p_pick looks at, and how it chooses
p_probe_ram: = $0161           ; the probe of a slot, copied there from probe_code (below)

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
switch:
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
  .ifdef placer
  CPY #place_text
  BNE .text
  JMP place
.text:
  .endif
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
  LDX #too_low-errors          ; below: the error, from $0100
  JMP refuse
.room:
  LDA #$83                     ; OSBYTE 131: PAGE, in X and Y
  JSR osbyte
  STX w0
  STY w1
  LDX w3
  LDA commands+3,X             ; the start address, where the program's memory starts, less PAGE
  CMP w0
  LDA commands+4,X
  SBC w1
  BCS .page
  LDX #too_high-errors         ; below PAGE: the error, before anything is copied over the
  JMP refuse                   ; filing system's workspace
.page:
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
; The errors when HIMEM is below the program's memory and when PAGE is above where it starts, and
; the placer's when a tool's regions need more sideways RAM than there is: BRK, the number, the
; text, 0.
errors:
too_low:
  .byte $00, $00
  .asciiz "Mode 7 needed"
too_low_end:
too_high:
  .byte $00, $00
  .asciiz "PAGE too high"
too_high_end:
  .ifdef placer
too_few:
  .byte $00, $00
  .asciiz "Too little sideways RAM"
  .endif

; Raise the error that starts at errors + X, copied to $0100, as a sideways ROM must: its BRK and
; number, then its text to the 0.
refuse:
  LDA errors,X
  STA $0100
  INX
  LDA errors,X
  STA $0101
  INX
  LDY #$02
.copy:
  LDA errors,X
  STA $0100,Y
  BEQ .raise
  INX
  INY
  BNE .copy
.raise:
  JMP $0100
  .endif

  .ifdef placer
; The placer of a tool's dynamic regions (lathe/docs/bbc.md, "One image for every machine with
; sideways RAM"; lathe/host/lk_dyn.py has the list's form), one for every tool of the image: a
; tool's `$start` calls rt_place.place, which puts the list's address at $A8/$A9 and asks with
; OSBYTE 143, X = text_call and Y = place_text (text 255, the linker's error 0, which is none),
; before anything else of the tool runs. It reads PAGE and HIMEM, refuses PAGE above the fixed
; part and HIMEM below the tool's ranges (MOS errors from $0100), and knows the free areas: main
; RAM's (from PAGE to the fixed part, the free areas the list gives, from the end of the ranges
; to HIMEM), then each slot of free sideways RAM's, the window $8000-$BFDF (p_find). Then each
; region in the list's order, at an address with the low byte it is linked at:
;
; - one with a capacity variable gets the area that gives it the most bytes, if that is at least
;   its size as linked, and all of that area; the bytes less where its last variable starts are
;   written in the variable, the room that variable has (so such a region is best last);
; - any other goes in the first area that holds it: main RAM if it fits there, else sideways RAM;
; - none in a bank of the module (a value of $10 or more) moves, and one with a capacity there
;   has the size it is linked with.
;
; A region that no area holds is refused: `Too little sideways RAM`. For each region it adds the
; pages moved to each high byte the list names and makes each of its blocks' banks the slot it is
; in, or the module's own slot ($F4 now) in main RAM. Its variables are at $0100-$015B and the
; probe after them, the bottom of the stack's page, which nothing uses while a tool starts (an
; error copied to $0100 ends it). It ends through `claim`.
place:
  LDA #$83                     ; OSBYTE 131: PAGE, in X and Y
  JSR osbyte
  STX p_page
  STY p_page+1
  JSR p_word
  STA p_code_lo
  STX p_code_lo+1
  JSR p_word
  STA p_top
  STX p_top+1
  LDA p_code_lo                ; PAGE above the fixed part: refused
  CMP p_page
  LDA p_code_lo+1
  SBC p_page+1
  BCS .page_low
  LDX #too_high-errors
  JMP refuse
.page_low:
  LDA #$84                     ; OSBYTE 132: HIMEM
  JSR osbyte
  STX p_himem
  STY p_himem+1
  CPX p_top                    ; HIMEM below the end of the ranges: refused
  TYA
  SBC p_top+1
  BCS .himem_high
  LDX #too_low-errors
  JMP refuse
.himem_high:
  LDA #$00                     ; the free areas: PAGE to the fixed part, the list's, HIMEM's
  STA p_areas
  LDA p_page
  STA w2
  LDA p_page+1
  STA w3
  LDA p_code_lo
  SEC
  SBC #$01
  STA w4
  LDA p_code_lo+1
  SBC #$00
  STA w5
  JSR p_add_main
  JSR p_byte
  STA p_regions
.areas:
  LDA p_regions
  BEQ .areas_read
  DEC p_regions
  JSR p_word
  STA w2
  STX w3
  JSR p_word
  STA w4
  STX w5
  JSR p_add_main
  JMP .areas
.areas_read:
  LDA p_top
  STA w2
  LDA p_top+1
  STA w3
  LDA p_himem
  SEC
  SBC #$01
  STA w4
  LDA p_himem+1
  SBC #$00
  STA w5
  JSR p_add_main
  JSR p_find                   ; the free sideways RAM's
  JSR p_byte                   ; each region: its bank's value, its block, its capacity variable,
  STA p_regions                ; its high bytes and its blocks' banks
.region:
  LDA p_regions
  BNE .more
  JMP claim
.more:
  DEC p_regions
  JSR p_byte                   ; the bank's value
  STA p_value
  STA p_new
  JSR p_word
  STA p_linked
  STX p_linked+1
  JSR p_word
  STA w4
  STX w5
  JSR p_word                   ; its capacity variable, and if it has one where its last starts
  STA p_room
  STX p_room+1
  ORA p_room+1
  BEQ .no_room
  JSR p_word
  STA p_offset
  STX p_offset+1
  JSR p_word
  STA p_least
  STX p_least+1
  JSR p_word
  STA p_ceiling
  STX p_ceiling+1
.no_room:
  LDA w4                       ; the bytes it has where it is linked
  STA p_grant
  LDA w5
  STA p_grant+1
  LDA #$00
  STA p_pages
  LDA w4
  ORA w5
  BEQ .placed                  ; nothing to move
  LDA p_value
  CMP #$10
  BCS .placed                  ; a bank of the module: it stays
  LDA p_room
  ORA p_room+1
  BEQ .fixed_size
  LDA p_least                  ; with a capacity: at least its least
  STA w4
  LDA p_least+1
  STA w5
  LDA p_ceiling
  ORA p_ceiling+1
  BNE .bounded
  JSR p_take_most
  JMP .taken
.bounded:
  JSR p_take_bounded
  JMP .taken
.fixed_size:
  JSR p_take
.taken:
  BCC .room
  LDX #too_few-errors          ; no area holds it
  JMP refuse
.room:
  LDA p_slot,X                 ; the slot of the area, or main RAM: the module's own
  BPL .slot
  LDA romcopy
.slot:
  STA p_new
  LDA p_goes+1                 ; the pages it moves
  SEC
  SBC p_linked+1
  STA p_pages
.placed:
  LDA p_room
  STA w2
  LDA p_room+1
  STA w3
  ORA w2
  BEQ .places
  LDY #$00                     ; its capacity variable: the bytes given (or linked, where it
  LDA p_grant                  ; stays), less where its last variable starts
  SEC
  SBC p_offset
  STA (w2),Y
  INY
  LDA p_grant+1
  SBC p_offset+1
  STA (w2),Y
.places:
  JSR p_count
.high:
  JSR p_count_down
  BEQ .highs_done
  JSR p_place
  LDA p_pages
  BEQ .high
  CLC
  LDY #$00
  ADC (w2),Y
  STA (w2),Y
  JMP .high
.highs_done:
  JSR p_count
.bank:
  JSR p_count_down
  BNE .bank_place
  JMP .region
.bank_place:
  JSR p_place
  LDA p_new
  LDY #$00
  STA (w2),Y
  JMP .bank

; The free sideways RAM's areas, after main RAM's: each slot, from 0 up, that is not the module's,
; that the MOS's table of ROM types (OSBYTE 170) does not mark, that holds no ROM header (one
; loaded since the last BREAK) and that keeps what is written to it, two patterns (neither of
; which an empty socket's open bus gives) and then its own byte again (p_probe_ram, from
; probe_code), as far as there is room in the table of areas.
p_find:
  LDX #probe_code_end-probe_code-$01
.copy:
  LDA probe_code,X
  STA p_probe_ram,X
  DEX
  BPL .copy
  LDA #$AA                     ; OSBYTE 170: the table of ROM types, in X and Y
  LDX #$00
  LDY #$FF
  JSR osbyte
  STX w6
  STY w7
  LDX #$00
.slot:
  CPX romcopy
  BEQ .next                    ; the module's own
  TXA
  TAY
  LDA (w6),Y
  BNE .next                    ; a ROM the MOS found
  JSR p_probe_ram              ; Y not 0: RAM
  TYA
  BEQ .next
  STX p_new
  LDA #$00                     ; the window, $8000-$BFDF
  STA w2
  LDA #$80
  STA w3
  LDA #$DF
  STA w4
  LDA #$BF
  STA w5
  TXA
  JSR p_add_area
  LDX p_new
.next:
  INX
  CPX #$10
  BCC .slot
  RTS

; Copied to p_probe_ram and run there, with interrupts off, since it selects slot X in the window:
; Y = 1 if the slot holds no ROM header and keeps what is written at $8008 (put back after), else
; 0. Only relative branches, so that it runs where it is copied to. X is kept.
probe_code:
  PHP
  SEI
  LDA romcopy
  PHA
  STX romcopy
  STX romsel
  LDY $8007                    ; a header's copyright offset: 0, "(C"
  LDA $8000,Y
  BNE .unmarked
  LDA $8001,Y
  CMP #$28
  BNE .unmarked
  LDA $8002,Y
  CMP #$43
  BNE .unmarked
  LDY #$00                     ; a ROM image
  BEQ .back
.unmarked:
  LDA $8008
  PHA
  LDY #$00
  LDA #$55
  STA $8008
  CMP $8008
  BNE .restore
  LDA #$AA
  STA $8008
  CMP $8008
  BNE .restore
  INY                          ; RAM
.restore:
  PLA
  STA $8008
.back:
  PLA
  STA romcopy
  STA romsel
  PLP
  RTS
probe_code_end:

; The next byte of the list, in A, the Z flag as it; Y is lost.
p_byte:
  LDY #$00
  LDA (w0),Y
  INC w0
  BNE .done
  INC w1
.done:
  CMP #$00
  RTS

; The next word of the list, in A (low) and X (high).
p_word:
  JSR p_byte
  PHA
  JSR p_byte
  TAX
  PLA
  RTS

; The next place: p_before the distance in the byte, or the word after a byte 0; in w2/w3.
p_place:
  JSR p_byte
  BEQ .word
  CLC
  ADC p_before
  STA p_before
  BCC .set
  INC p_before+1
  JMP .set
.word:
  JSR p_word
  STA p_before
  STX p_before+1
.set:
  LDA p_before
  STA w2
  LDA p_before+1
  STA w3
  RTS

; The next list of places: their count in p_number, and p_before 0.
p_count:
  JSR p_word
  STA p_number
  STX p_number+1
  LDA #$00
  STA p_before
  STA p_before+1
  RTS

; One place fewer in p_number: Z set when none was left.
p_count_down:
  LDA p_number
  ORA p_number+1
  BEQ .counted
  LDA p_number
  BNE .low
  DEC p_number+1
.low:
  DEC p_number
  LDA #$01                     ; Z clear: a place to read
.counted:
  RTS

; A free area of main RAM from w2/w3 to w4/w5 (p_add_area).
p_add_main:
  LDA #$FF
; A free area from w2/w3 to w4/w5, in slot A ($FF: main RAM), if there is room for it in the table
; and it is not empty.
p_add_area:
  LDX p_areas
  CPX #p_max_areas
  BCS .end
  STA p_slot,X
  LDA w4                       ; last < first: empty
  CMP w2
  LDA w5
  SBC w3
  BCC .end
  LDA w2
  STA p_first_lo,X
  LDA w3
  STA p_first_hi,X
  LDA w4
  STA p_last_lo,X
  LDA w5
  STA p_last_hi,X
  INC p_areas
.end:
  RTS

; Where in area X a block of w4/w5 bytes with p_linked's low byte goes: in p_goes, from the area's
; first page at that low byte, or the next page if that is below its first byte, and its last
; byte in p_end; the carry set if the area holds it, else clear. X is kept.
p_fit:
  LDA p_linked                 ; the area's first page, at the low byte linked
  STA p_goes
  LDA p_first_hi,X
  STA p_goes+1
  LDA p_goes                   ; below the area's first: a page on
  CMP p_first_lo,X
  BCS .end
  INC p_goes+1
  BEQ .none                    ; past $FFFF
.end:
  LDA p_goes                   ; the last byte it takes: p_goes + size - 1
  CLC
  ADC w4
  STA p_end
  LDA p_goes+1
  ADC w5
  STA p_end+1
  BCS .none
  LDA p_end
  SEC
  SBC #$01
  STA p_end
  BCS .fits
  DEC p_end+1
.fits:
  LDA p_last_lo,X              ; at most the area's last
  CMP p_end
  LDA p_last_hi,X
  SBC p_end+1
  RTS                          ; the carry set if the end is not past the last
.none:
  CLC
  RTS

; w4/w5 bytes at an address with p_linked's low byte, from the first free area that holds them:
; the address in p_goes, the area in X and the carry clear, or the carry set if none does.
p_take:
  LDX #$00
.area:
  CPX p_areas
  BCS .none
  JSR p_fit
  BCC .next
  LDA p_end                    ; taken: the area starts after it
  CLC
  ADC #$01
  STA p_first_lo,X
  LDA p_end+1
  ADC #$00
  STA p_first_hi,X
  CLC
  RTS
.next:
  INX
  JMP .area
.none:
  SEC
  RTS

; As p_take, but the area that holds w4/w5 bytes and gives the most, all of it: from p_goes to the
; area's last byte, that many bytes in p_grant (the first such area if two give as many).
p_take_most:
  LDA #$00                     ; of every area, the most
  JSR p_pick
  BCS .none
  LDA p_last_lo,X              ; all of it taken
  CLC
  ADC #$01
  STA p_first_lo,X
  LDA p_last_hi,X
  ADC #$00
  STA p_first_hi,X
  CLC
.none:
  RTS

; As p_take, for a region with a ceiling: of main RAM's areas that hold w4/w5 bytes the one that
; gives the most, or if none does, of sideways RAM's the one that gives the least; as many bytes
; as it gives, at most p_ceiling, in p_grant.
p_take_bounded:
  LDA #$01                     ; main RAM's, the most
  JSR p_pick
  BCC .chosen
  LDA #$02                     ; sideways RAM's, the least
  JSR p_pick
  BCS .none
.chosen:
  LDA p_ceiling                ; at most the ceiling
  CMP p_grant
  LDA p_ceiling+1
  SBC p_grant+1
  BCS .within
  LDA p_ceiling
  STA p_grant
  LDA p_ceiling+1
  STA p_grant+1
.within:
  LDA p_goes                   ; taken: the area starts after it
  CLC
  ADC p_grant
  STA p_first_lo,X
  LDA p_goes+1
  ADC p_grant+1
  STA p_first_hi,X
  CLC
.none:
  RTS

; The area that holds w4/w5 bytes at p_linked's low byte and, by A: 0, of every area, gives the
; most; 1, of main RAM's, the most; 2, of sideways RAM's, the least (the first if two give as
; many). The area in X, its place in p_goes, what it gives in p_grant and the carry clear; or
; the carry set if no such area holds them.
p_pick:
  STA p_kind
  LDA #$FF
  STA p_best
  LDX #$00
.area:
  CPX p_areas
  BCS .chosen
  LDA p_kind
  BEQ .any
  LSR                          ; 1: main RAM's alone; 2: sideways RAM's alone
  BCC .sideways
  LDA p_slot,X
  BPL .next
  BMI .any
.sideways:
  LDA p_slot,X
  BMI .next
.any:
  JSR p_fit
  BCC .next
  JSR p_given
  LDA p_best
  BMI .better                  ; the first that holds them
  LDA p_kind
  CMP #$02
  BEQ .fewer
  LDA p_most                   ; more than the best so far
  CMP p_grant
  LDA p_most+1
  SBC p_grant+1
  BCS .next
  BCC .better
.fewer:
  LDA p_grant                  ; fewer than the best so far
  CMP p_most
  LDA p_grant+1
  SBC p_most+1
  BCS .next
.better:
  STX p_best
  LDA p_grant
  STA p_most
  LDA p_grant+1
  STA p_most+1
.next:
  INX
  JMP .area
.chosen:
  LDX p_best
  BMI .none
  JSR p_fit                    ; its place again, and what it gives
  JSR p_given
  CLC
  RTS
.none:
  SEC
  RTS

; The bytes area X gives from p_goes to its last, in p_grant. X is kept.
p_given:
  LDA p_last_lo,X
  SEC
  SBC p_goes
  STA p_grant
  LDA p_last_hi,X
  SBC p_goes+1
  STA p_grant+1
  INC p_grant
  BNE .end
  INC p_grant+1
.end:
  RTS
  .endif


; An error's text: a tool's ROM form asks for text Y with OSBYTE 143, X = text_call (lathe/rt/
; bbc.lth, error_text), and the module writes ": " and the text with OSWRCH and claims the call;
; when no ROM claims it, nothing is written, and the error is its number alone. Text n is the
; compiler's error n, text 255 - n the linker's. The texts (lathe/host/driver/msgpack.py packs
; them from the host's tables) are in one part or more, each the code of lathe/rt/bbc/texts.asm
; and its tables, which bbcrom.py puts wherever there is room, in this bank or another: the table
; of the parts, after the tables below, gives for each the first text it holds, its bank and its
; entry less 1, in order of their first texts (the first part's is 0). bbcrom.py defines which
; way it is entered: `part_at_home`, the part's address, when there is one part and it is in this
; bank (a JMP to it); else `parts_away`, and `one_part_away` for one part in another bank or
; `several_parts` for more, when the part is looked for. This finds the part of
; text Y and enters its bank there with Y the texts before it in the part: the return address
; and a byte pushed, it jumps to `switch`, the read of $BFF0 + X in the reserved bytes, after
; which the same bytes of the part's bank pull the byte and return to the part. The part ends
; through `claim`, which selects the bank of entry again.
text:
  LDA #$3A                     ; ": "
  JSR oswrch
  LDA #$20
  JSR oswrch
  .ifdef part_at_home
  JMP part_at_home             ; the one part, in this bank: Y is the texts before it
  .endif
  .ifdef several_parts
  LDX #text_parts-1
.part:
  TYA
  CMP part_first,X
  BCS .found                   ; Y is the part's first text or after it
  DEX
  BPL .part                    ; always found: the first part's first text is 0
.found:
  SEC
  SBC part_first,X
  TAY                          ; the texts before it in the part
  .endif
  .ifdef one_part_away
  LDX #$00                     ; one part, from text 0: Y is the texts before it
  .endif
  .ifdef parts_away
  LDA part_entry_high,X
  PHA
  LDA part_entry_low,X
  PHA                          ; the part's entry less 1, for the RTS after switch
  PHA                          ; a byte for its PLA
  LDA part_bank,X
  TAX
  JMP switch
  .endif

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
