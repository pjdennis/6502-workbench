; Michael's ROM (32 KB EEPROM at $8000): at reset it receives an upload in format 3
; (firmware/lib/serial/upload_v3.inc, tools/upload/upload_frame.py) and runs it. Uploads go
; to zero page, and from $0200 up to the interrupt page ($3F00, where the IRQ vector points). Uploaded programs
; can call the LCD and keyboard services (michael_services.inc) through the vector table at
; $F006 (michael_rom.inc): the asm2 environment's entry points, so the editor's
; direct_io build runs on it; exit comes back here.
;
; Build:   firmware/vasm -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc
;              -o michael_rom.bin firmware/boards/michael/michael_rom.s
; Program: minipro -p AT28C256 -w michael_rom.bin

  .include base_config_v2.inc
  .include michael_rom.inc
  .include michael_editor_layout.inc

EXTEND_CHARACTER_SET = 1                  ; '~' and '\' as custom characters (the services')
DISPLAY_INTERRUPTS_FLAG = ROM_FLAGS       ; The LCD routines, shared by the loader and the services
BPS_HUNDREDS      = 576                   ; 57600 bps
UPLOAD_RAM_START  = $0200
INTERRUPT_ROUTINE = INTERRUPT_VECTOR_TARGET

; Zero page: the loader's block, each variable after the one before (upload_v3.inc checks them,
; and stashes the block while placing an upload, so the upload may load it too)
UPLOAD_ZP_START      = $00
DISPLAY_STRING_PARAM = UPLOAD_ZP_START            ; 2 bytes
UPLOAD_P             = DISPLAY_STRING_PARAM + 2   ; 2 bytes
WAITING_FOR_SHIFT    = UPLOAD_P + 2               ; 1 byte
UPLOAD_STATE         = WAITING_FOR_SHIFT + 1      ; 1 byte
UPLOAD_COUNT         = UPLOAD_STATE + 1           ; 1 byte
UPLOAD_SEEN          = UPLOAD_COUNT + 1           ; 2 bytes
UPLOAD_SHOWN         = UPLOAD_SEEN + 2            ; 2 bytes
UPLOAD_SHOWN_ENTRY   = UPLOAD_SHOWN + 2           ; 1 byte
UPLOAD_TICKS         = UPLOAD_SHOWN_ENTRY + 1     ; 1 byte
UPLOAD_ENTRY         = UPLOAD_TICKS + 1           ; 1 byte
UPLOAD_ENTRY_DATA    = UPLOAD_ENTRY + 1           ; 2 bytes
UPLOAD_ENTRY_NEXT    = UPLOAD_ENTRY_DATA + 2      ; 2 bytes
UPLOAD_DATA          = UPLOAD_ENTRY_NEXT + 2      ; 2 bytes
UPLOAD_END           = UPLOAD_DATA + 2            ; 2 bytes
UPLOAD_SOURCE        = UPLOAD_END + 2             ; 2 bytes
UPLOAD_FROM          = UPLOAD_SOURCE + 2          ; 2 bytes
UPLOAD_TO            = UPLOAD_FROM + 2            ; 2 bytes
UPLOAD_LENGTH        = UPLOAD_TO + 2              ; 2 bytes
UPLOAD_LIMIT         = UPLOAD_LENGTH + 2          ; 2 bytes
UPLOAD_FLAGS         = UPLOAD_LIMIT + 2           ; 1 byte
CHECKSUM_VALUE       = UPLOAD_FLAGS + 1           ; 2 bytes
TEMP                 = CHECKSUM_VALUE + 2         ; 1 byte
UPLOAD_ZP_END        = TEMP + 1

UPLOAD_BEFORE_RUN    = services_reset      ; Nothing started, for the upload
SERVICES_EXIT        = reset

  .include serial_receive_timing.inc

  .org $8000

  ; Delay loops first: page-aligned, so their timing crosses no page boundary
  .include delay_routines.inc

reset:
  sei
  cld
  ldx #$ff
  txs
  jsr services_reset
  jmp initialize_machine          ; Sets up the VIA's ports, then jumps to program_start

  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc
  .include display_hex.inc

rom_message:   .asciiz 'Michael ROM 4'

program_start:
  jsr reset_and_enable_display_no_cursor
  lda #<rom_message
  ldx #>rom_message
  jsr display_string
  jmp upload_v3                   ; Shows "Ready" under it while it waits

  .include upload_v3.inc

nmi:
  rti

; The services, behind the vector table at $F006 (michael_rom.inc)
  .org SVC_BASE + $06
  .include michael_services.inc

  .if ROM_IRQ_JMP != INTERRUPT_ROUTINE
  fail "ROM_IRQ_JMP (michael_rom.inc) isn't where the IRQ vector points"
  .endif
  .if ROM_RAM_END > MICHAEL_EDITOR_SPARE
  fail "The services' RAM runs into the editor's (MICHAEL_EDITOR_SPARE)"
  .endif

  .org $fffa
  .word nmi
  .word reset
  .word INTERRUPT_ROUTINE
