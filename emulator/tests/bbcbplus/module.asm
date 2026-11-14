; bbcbplus test: one 16 KB bank of a banked module image.
;
; define:BANK0 builds bank 0: a sideways ROM header and a service handler
; that claims *HELLO (service call 4). It copies a trampoline into main
; RAM ($0400) and calls it; from there, where switching banks does not
; pull the code from under the CPU, the trampoline selects bank 3, calls
; the routine at $8100 in bank 3, and selects bank 0 again.
; define:BANK3 builds bank 3: that routine, which prints a line.
; define:DIRECT16 switches as the direct16 scheme does (a read of $BFF0+n
; selects bank n), define:CC128 as the Computer Concepts 128K carrier (a
; read of $BFE0 selects bank 0, one of $BF80-$BF9F bank 3).
; build.py puts the banks together into a 128 KB image.

oswrch: = $FFEE
osnewl: = $FFE7
cli_ptr: = $F2
romcopy: = $F4
bank3_hello: = $8100
tramp_ram: = $0400

* = $8000
  .ifdef BANK0
header:
  .byte $00, $00, $00          ; no language entry
  JMP service                  ; the service entry
  .byte $82                    ; type: a service entry, 6502 code
  .byte copyright-header       ; the copyright string's offset
  .byte $01                    ; version
  .byte "Test module"          ; title
copyright:
  .byte $00
  .asciiz "(C) 6502-workbench"

service:
  CMP #$04
  BEQ .command
  RTS
.command:
  PHA
  TYA
  PHA
  LDX #$00
.compare:
  LDA (cli_ptr),Y
  AND #$DF
  CMP hello,X
  BNE .no
  INY
  INX
  CPX #$05
  BNE .compare
  LDA (cli_ptr),Y
  CMP #$0D
  BEQ .yes
  CMP #$20
  BNE .no
.yes:
  PLA
  PLA
  LDX #tramp_end-tramp-$01
.copy:
  LDA tramp,X
  STA tramp_ram,X
  DEX
  BPL .copy
  JSR tramp_ram
  LDX romcopy
  LDA #$00
  RTS
.no:
  PLA
  TAY
  PLA
  LDX romcopy
  RTS

hello:
  .byte "HELLO"

; Copied to main RAM and run there: it uses no address of its own
tramp:
  .ifdef DIRECT16
  LDA $BFF3
  .endif
  .ifdef CC128
  LDA $BF80
  .endif
  JSR bank3_hello
  .ifdef DIRECT16
  LDA $BFF0
  .endif
  .ifdef CC128
  LDA $BFE0
  .endif
  RTS
tramp_end:
  .endif

  .ifdef BANK3
  .asciiz "bank 3"
* = $8100
print:
  LDX #$00
.loop:
  LDA msg,X
  BEQ .done
  JSR oswrch
  INX
  BNE .loop
.done:
  JMP osnewl
msg:
  .asciiz "Hello from bank 3"
  .endif

* = $BFFF
  .byte $FF
