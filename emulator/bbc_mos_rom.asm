; The MOS ROM of the emulator's --machine bbcbplus, $C000-$FFFF.
;
; Not Acorn's MOS: a small stand-in with the documented entry points at
; their real addresses, each jumping through its vector in page 2 as the
; real MOS does, the vectors set to defaults at reset, and default
; handlers that end in a host trap, where the emulator does the work in C
; (emulator/bbc_mos.c).
;
; A host trap is the byte $02 at a label named t_<name>, right after a
; NOP. The emulator acts on it only when the instruction it has just run
; is that NOP; reaching a trap byte any other way stops the run as a
; fault. bbc_mos_to_c.py checks every trap has its NOP.
;
; Written for the repository's own assembler (asm/17; built here with its
; Python work-alike asm/pyasm.py by emulator/bbc_mos_to_c.py, which writes
; emulator/bbc_mos_rom_generated.h). Mnemonics are upper case; constants
; come before their use so they assemble to zero page where they can.

; ---- page 2 vectors ----
userv: = $0200
brkv: = $0202
irq1v: = $0204
irq2v: = $0206
cliv: = $0208
bytev: = $020A
wordv: = $020C
wrchv: = $020E
rdchv: = $0210
filev: = $0212
argsv: = $0214
bgetv: = $0216
bputv: = $0218
gbpbv: = $021A
findv: = $021C
fscv: = $021E
romtab: = $02A1
brk_rom: = $024A
language: = $028C

; ---- zero page the MOS documents ----
osbyte_a: = $EF
osbyte_x: = $F0
osbyte_y: = $F1
cli_ptr: = $F2
romcopy: = $F4
rdrm_ptr: = $F6
irq_a: = $FC
err_ptr: = $FD

romsel: = $FE30
svc_entry: = $8003

* = $C000
mos_title:
  .asciiz "6502-workbench MOS for the emulated BBC B+ (not Acorn's)"

; ---- reset ----
reset:
  SEI
  CLD
  LDX #$FF
  TXS
  LDX #$35
.vec:
  LDA vectab,X
  STA userv,X
  DEX
  BPL .vec
  NOP
; C: the ROM type table, $F4 and ROMSEL, then the command (through OSCLI)
; or the program, with exit_ret as the return address
t_reset:
  .byte $02

; The command or the program returned: the run ends with exit status 0
exit_ret:
  NOP
t_exit:
  .byte $02

; ---- OSCLI ----
cli_default:
  STX cli_ptr
  STY cli_ptr+$01
  NOP
; C: a built-in command, a file to run, or one for the ROMs (cli_svc)
t_cli:
  .byte $02
  RTS

; Service call 4 (unrecognised command), Y = the command's offset from
; ($F2); unclaimed, C tries the file and otherwise raises Bad command
cli_svc:
  LDX #$04
  JSR svc
  BNE .unclaimed
  RTS
.unclaimed:
  NOP
t_cli_file:
  .byte $02
  RTS

; *HELP: service call 9, Y = the offset of its argument from ($F2). Every
; ROM is offered it and none claims it; the MOS prints nothing of its own
cli_help:
  LDX #$09
  JMP svc

; ---- OSBYTE ----
byte_default:
  STA osbyte_a
  STX osbyte_x
  STY osbyte_y
  NOP
t_byte:
  .byte $02
  RTS

; OSBYTE 143: X = the service call, Y = its argument
byte_svc:
  JMP svc

; Not the MOS's: offered to the ROMs as service call 7 with A, X and Y in
; $EF, $F0 and $F1. Claimed: X from $F0, Y as the ROM left it. Unclaimed:
; X = $FF, Y as given, and V set
byte_unknown:
  LDX #$07
  JSR svc
  BEQ .claimed
  LDX #$FF
  LDY osbyte_y
  BIT vbit
  LDA osbyte_a
  RTS
.claimed:
  LDX osbyte_x
  CLV
  LDA osbyte_a
  RTS

; OSBYTE 142: C has selected the language ROM and set A = 1
byte_lang:
  JMP $8000

vbit:
  .byte $40

; ---- OSWORD ----
word_default:
  STA osbyte_a
  STX osbyte_x
  STY osbyte_y
  NOP
t_word:
  .byte $02
  RTS

; Not the MOS's: service call 8 with A, X and Y in $EF, $F0 and $F1
word_unknown:
  LDX #$08
  JSR svc
  LDA osbyte_a
  LDX osbyte_x
  LDY osbyte_y
  RTS

; ---- character I/O ----
wrch_default:
  NOP
t_wrch:
  .byte $02
  RTS

rdch_default:
  NOP
t_rdch:
  .byte $02
  RTS

; ---- the filing system (the host directory of --disk) ----
file_default:
  NOP
t_file:
  .byte $02
  RTS

args_default:
  NOP
t_args:
  .byte $02
  RTS

bget_default:
  NOP
t_bget:
  .byte $02
  RTS

bput_default:
  NOP
t_bput:
  .byte $02
  RTS

gbpb_default:
  NOP
t_gbpb:
  .byte $02
  RTS

find_default:
  NOP
t_find:
  .byte $02
  RTS

rts_only:
  RTS

; ---- service calls ----
; X = the call, Y = its argument. Offered to each ROM with a service entry
; (bit 7 of its type in $02A1+n), slot 15 down to 0: the ROM selected (in
; $F4 and ROMSEL), A = the call, X = the ROM's slot, Y as given. A ROM
; claims it by returning A = 0. The ROM selected before is selected again.
; Returns A = X = 0 if claimed, else the call; Z set if claimed.
svc:
  LDA romcopy
  PHA
  TXA
  LDX #$0F
.loop:
  PHA
  LDA romtab,X
  BMI .call
  PLA
  JMP .next
.call:
  PLA
  STX romcopy
  STX romsel
  JSR svc_entry
  LDX romcopy
  CMP #$00
  BEQ .end
.next:
  DEX
  BPL .loop
.end:
  TAX
  PLA
  STA romcopy
  STA romsel
  TXA
  RTS

; ---- OSRDRM: the byte at ($F6) in ROM Y ----
osrdrm:
  LDA romcopy
  PHA
  STY romcopy
  STY romsel
  LDY #$00
  LDA (rdrm_ptr),Y
  TAY
  PLA
  STA romcopy
  STA romsel
  TYA
  RTS

; ---- IRQ and BRK ----
; No interrupts are generated. BRK, as MOS 1.20 does it: $FD/$FE to the
; error number (the byte after the BRK), $024A to the ROM selected then,
; $F0 to the stack pointer; service call 6; the language ROM ($028C)
; selected; then through BRKV with A and X as they were.
irq:
  STA irq_a
  PLA
  PHA
  AND #$10
  BNE .brk
  JMP (irq1v)
.brk:
  TXA
  PHA
  TSX
  LDA $0103,X
  CLD
  SEC
  SBC #$01
  STA err_ptr
  LDA $0104,X
  SBC #$00
  STA err_ptr+$01
  LDA romcopy
  STA brk_rom
  STX osbyte_x
  LDX #$06
  JSR svc
  LDX language
  STX romcopy
  STX romsel
  PLA
  TAX
  LDA irq_a
  CLI
  JMP (brkv)

irq1_default:
  JMP (irq2v)

irq2_default:
  LDA irq_a
nmi:
  RTI

; The default BRKV handler: C prints the error message to standard error
; and ends the run with exit status 1
brk_default:
  NOP
t_brk:
  .byte $02

; ---- errors the MOS raises: BRK, the number, the message, 0 ----
e_bad_command:
  .byte $00, 254
  .asciiz "Bad command"
e_bad_address:
  .byte $00, 252
  .asciiz "Bad address"
e_not_language:
  .byte $00, 0
  .asciiz "This is not a language"
e_os:
  .byte $00, 247
  .asciiz "OS 2.00"
e_file_not_found:
  .byte $00, 214
  .asciiz "File not found"
e_channel:
  .byte $00, 222
  .asciiz "Channel"
e_eof:
  .byte $00, 223
  .asciiz "EOF"
e_bad_name:
  .byte $00, 204
  .asciiz "Bad name"
e_too_many_open:
  .byte $00, 192
  .asciiz "Too many open files"
; --bbc-fs dfs: the DFS's own errors (emulator/NOTES-bbcbplus.md, "The filing system")
e_dfs_too_many_open:
  .byte $00, 192
  .asciiz "Too many open"
e_bad_drive:
  .byte $00, 205
  .asciiz "Bad drive"
e_cat_full:
  .byte $00, 190
  .asciiz "Cat full"
e_read_only:
  .byte $00, 193
  .asciiz "Read only"
e_disc_fault:
  .byte $00, 199
  .asciiz "Disc fault"
e_no_disk:
  .byte $00, 199
  .asciiz "No disk (--disk)"
e_unsupported:
  .byte $00, 255
  .asciiz "Not in this emulator's MOS"

; ---- the default vectors, copied to $0200-$0235 at reset ----
vectab:
  .word rts_only          ; USERV
  .word brk_default       ; BRKV
  .word irq1_default      ; IRQ1V
  .word irq2_default      ; IRQ2V
  .word cli_default       ; CLIV
  .word byte_default      ; BYTEV
  .word word_default      ; WORDV
  .word wrch_default      ; WRCHV
  .word rdch_default      ; RDCHV
  .word file_default      ; FILEV
  .word args_default      ; ARGSV
  .word bget_default      ; BGETV
  .word bput_default      ; BPUTV
  .word gbpb_default      ; GBPBV
  .word find_default      ; FINDV
  .word rts_only          ; FSCV
  .word rts_only          ; EVNTV
  .word rts_only          ; UPTV
  .word rts_only          ; NETV
  .word rts_only          ; VDUV
  .word rts_only          ; KEYV
  .word rts_only          ; INSV
  .word rts_only          ; REMV
  .word rts_only          ; CNPV
  .word rts_only          ; IND1V
  .word rts_only          ; IND2V
  .word rts_only          ; IND3V
vectab_end:

; --bbc-fs adfs: ADFS's own errors (emulator/NOTES-bbcbplus.md, "ADFS on the B+"). After
; everything else, so that adding them moved nothing of the ROM before them.
e_not_found:
  .byte $00, $D6
  .asciiz "Not found"
e_already_open:
  .byte $00, $C2
  .asciiz "Already open"
e_already_exists:
  .byte $00, $C4
  .asciiz "Already exists"
e_dir_full:
  .byte $00, $B3
  .asciiz "Dir full"
e_dir_not_empty:
  .byte $00, $B4
  .asciiz "Dir not empty"
e_disc_full:
  .byte $00, $C6
  .asciiz "Disc full"
e_compaction:
  .byte $00, $98
  .asciiz "Compaction required"
e_map_full:
  .byte $00, $99
  .asciiz "Map full"
e_wild_cards:
  .byte $00, $FD
  .asciiz "Wild cards"
e_not_open_for_update:
  .byte $00, $C1
  .asciiz "Not open for update"
e_outside_file:
  .byte $00, $B7
  .asciiz "Outside file"

; ---- the entry points, at the real MOS's addresses ----
* = $FFB6
  .byte $36               ; length of the default vector table
  .word vectab            ; its address
osrdrm_entry:             ; $FFB9 OSRDRM
  JMP osrdrm
vduchr_entry:             ; $FFBC VDUCHR
  JMP e_unsupported
oseven_entry:             ; $FFBF OSEVEN
  JMP e_unsupported
gsinit_entry:             ; $FFC2 GSINIT
  JMP e_unsupported
gsread_entry:             ; $FFC5 GSREAD
  JMP e_unsupported
nvrdch_entry:             ; $FFC8 NVRDCH
  JMP rdch_default
nvwrch_entry:             ; $FFCB NVWRCH
  JMP wrch_default
osfind:                   ; $FFCE
  JMP (findv)
osgbpb:                   ; $FFD1
  JMP (gbpbv)
osbput:                   ; $FFD4
  JMP (bputv)
osbget:                   ; $FFD7
  JMP (bgetv)
osargs:                   ; $FFDA
  JMP (argsv)
osfile:                   ; $FFDD
  JMP (filev)
osrdch:                   ; $FFE0
  JMP (rdchv)
osasci:                   ; $FFE3
  CMP #$0D
  BNE oswrch
osnewl:                   ; $FFE7
  LDA #$0A
  JSR oswrch
  LDA #$0D
oswrch:                   ; $FFEE
  JMP (wrchv)
osword:                   ; $FFF1
  JMP (wordv)
osbyte:                   ; $FFF4
  JMP (bytev)
oscli:                    ; $FFF7
  JMP (cliv)
  .word nmi               ; $FFFA
  .word reset             ; $FFFC
  .word irq               ; $FFFE
