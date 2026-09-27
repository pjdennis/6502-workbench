; Michael's ROM (32 KB EEPROM at $8000): at reset it receives an upload in format 2
; (firmware/lib/serial/upload_v2.inc, tools/upload/upload_frame.py) and runs it. Uploads go
; from $0200 up to the interrupt page ($3F00, where the IRQ vector points). Uploaded programs
; can call the LCD and keyboard services (michael_services.inc) through the vector table at
; $F006 (michael_rom_vectors.inc): the asm2 environment's entry points, so the editor's
; direct_io build runs on it; exit comes back here.
;
; Build:   firmware/vasm -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc
;              -o michael_rom.bin firmware/boards/michael/michael_rom.s
; Program: minipro -p AT28C256 -w michael_rom.bin

  .include base_config_v2.inc

EXTEND_CHARACTER_SET = 1                  ; '~' and '\' as custom characters (the services')
BPS_HUNDREDS      = 576                   ; 57600 bps
UPLOAD_RAM_START  = $0200
INTERRUPT_ROUTINE = INTERRUPT_VECTOR_TARGET

; Zero page, the loader's until the upload runs
DISPLAY_STRING_PARAM = $00 ; 2 bytes
UPLOAD_P             = $02 ; 2 bytes
WAITING_FOR_SHIFT    = $04 ; 1 byte
UPLOAD_POS           = $05 ; 2 bytes
UPLOAD_TARGET        = $07 ; 2 bytes
UPLOAD_CHECK_FROM    = $09 ; 2 bytes
UPLOAD_END           = $0b ; 2 bytes
UPLOAD_START         = $0d ; 2 bytes
UPLOAD_FLAGS         = $0f ; 1 byte
UPLOAD_BLOCK         = $10 ; 1 byte
CHECKSUM_VALUE       = $11 ; 2 bytes
TEMP_P               = $13 ; 2 bytes
UPLOAD_LENGTH        = $15 ; 2 bytes
UPLOAD_ADDRESS       = $17 ; 2 bytes
UPLOAD_FROM          = $19 ; 2 bytes

  .include serial_receive_timing.inc

  .org $8000

  ; Delay loops first: page-aligned, so their timing crosses no page boundary
  .include delay_routines.inc

reset:
  sei
  cld
  ldx #$ff
  txs
  stz SERVICES_STARTED
  jmp initialize_machine          ; Sets up the VIA's ports, then jumps to program_start

  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc
  .include display_hex.inc

ready_message: .asciiz 'Ready.'
rom_message:   .asciiz 'Michael ROM 3'

program_start:
  jsr reset_and_enable_display_no_cursor
  lda #<rom_message
  ldx #>rom_message
  jsr display_string
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<ready_message
  ldx #>ready_message
  jsr display_string
  jmp upload_v2

  .include upload_v2.inc
  .include serial_receive_interrupt.inc   ; Copied to INTERRUPT_ROUTINE by upload_v2

nmi:
  rti

; The services, behind the vector table at $F006
  .include michael_rom_vectors.inc
SERVICES_STARTED = SERVICES_RAM_END        ; 1 byte, after the services' own RAM
SERVICES_EXIT    = reset

  .org SVC_BASE + $06
  .include michael_services.inc

  .if SERVICES_STARTED >= MICHAEL_EDITOR_SPARE
  fail "The services' RAM runs into the editor's (MICHAEL_EDITOR_SPARE)"
  .endif

  .org $fffa
  .word nmi
  .word reset
  .word INTERRUPT_ROUTINE
