; wendy2c boot MONITOR -- alternate boot ROM.
;
; Loads and runs programs from the simulated SPI "disk" (the emulator's
; --disk directory) over the $F800+ file-I/O OS calls. At boot it reads the
; disk file "autoexec" into a buffer and runs each line as a program name:
; load that file to $4000 and execute it. Programs return to the monitor when
; they exit (see the signature/return-stub contract below), so the monitor
; advances to the next autoexec line. When the lines are exhausted it halts.
;
; Memory: this ROM lives at $8000-$FFFF (the reset/config-$00 view). Programs
; load into the fixed lower-32K RAM at $4000; a launch stub in lower RAM
; switches the upper window to RAM bank $01 and jumps to $4000 (removing this
; ROM from the map -- hence the stub runs from RAM). On exit a program jumps
; to the return stub in lower RAM, which maps the ROM back (config $00) and
; re-enters the monitor. The wendy2 syslib's exit jumps to $0320 iff the
; monitor signature byte ($A5 at $02FF) is present, else it halts (STP), so
; the same programs still run standalone under the upload boot ROM.
; See prog8/WENDY2_DISK_BOOT_DESIGN.md.

  .include base_config_wendy2c.inc

; ---- OS-call ports ($F800+, provided by the emulator's --disk chip) ----
P_NAME   = $f800
P_NCLEAR = $f801
P_OPENR  = $f802
P_SEL    = $f804
P_READ   = $f805
P_EOF    = $f806
P_CLOSE  = $f808

; ---- zero page ----
DISPLAY_STRING_PARAM = $00      ; 2 bytes (display_string ABI)
DESTL  = $10
DESTH  = $11
HANDLE = $12
NP     = $14                    ; name pointer (2 bytes)
SBANK  = $16                    ; segment target bank
SLENL  = $17                    ; segment length (2 bytes)
SLENH  = $18
MAG0   = $19                    ; 3-byte magic peek
MAG1   = $1a
MAG2   = $1b
NSEG   = $1c                    ; segment count

PROGRAM_LOAD = $4000

; ---- fixed lower-RAM layout (untouched by loaded programs, which use $4000+) ----
MON_SIG      = $02ff            ; = $A5 tells the syslib a monitor is present
LAUNCH_RAM   = $0300            ; launch stub (bank $01 + jmp $4000)
RETURN_RAM   = $0320            ; return stub (config $00 + jmp run_next) -- exit target
SEG_STREAM_RAM = $0340          ; segment-stream stub (switch bank, stream, restore ROM)
CFGTAB_RAM   = $0380            ; logical bank 0..7 -> PORTB config byte
LINEBUF      = $0400            ; current program-name line
AX_POS       = $04fe            ; autoexec cursor
AX_LEN       = $04ff            ; autoexec length
AX_BUF       = $0500            ; autoexec contents (<=256 bytes)

  .org $8000

reset:
  sei
  cld
  ldx #$ff
  txs

  ; VIA: make banking bits + display pins outputs (config stays $00 = ROM)
  lda #BANK_MASK
  trb BANK_PORT
  tsb BANK_PORT + DDR_OFFSET
  lda #DISPLAY_BITS_MASK
  trb DISPLAY_DATA_PORT
  tsb DISPLAY_DATA_PORT + DDR_OFFSET
  lda #E
  trb DISPLAY_ENABLE_PORT
  tsb DISPLAY_ENABLE_PORT + DDR_OFFSET

  jsr reset_and_enable_display_no_cursor

  ; copy the launch + return stubs into fixed lower RAM
  ldx #0
.copy_launch:
  lda launch_stub_src,x
  sta LAUNCH_RAM,x
  inx
  cpx #(launch_stub_end - launch_stub_src)
  bne .copy_launch
  ldx #0
.copy_return:
  lda return_stub_src,x
  sta RETURN_RAM,x
  inx
  cpx #(return_stub_end - return_stub_src)
  bne .copy_return
  ldx #0
.copy_stream:
  lda seg_stream_src,x
  sta SEG_STREAM_RAM,x
  inx
  cpx #(seg_stream_end - seg_stream_src)
  bne .copy_stream
  ldx #0
.copy_cfgtab:
  lda cfgtab_src,x
  sta CFGTAB_RAM,x
  inx
  cpx #8
  bne .copy_cfgtab

  ; mark the monitor present so program exits return here
  lda #$a5
  sta MON_SIG

  jsr clear_display
  lda #<banner
  ldx #>banner
  jsr display_string

  ; read the whole "autoexec" file into AX_BUF
  jsr read_autoexec
  lda #0
  sta AX_POS
  ; fall through to run_next


; ---- run the next autoexec line (also the warm-start re-entry point) ----
run_next:
  ldx AX_POS
  cpx AX_LEN
  bcs .alldone
  ; copy one line (to LF/CR/EOF) into LINEBUF
  ldy #0
.cp:
  cpx AX_LEN
  bcs .lineend
  lda AX_BUF,x
  inx
  cmp #$0a
  beq .lineend
  cmp #$0d
  beq .lineend
  sta LINEBUF,y
  iny
  cpy #63
  bne .cp
.lineend:
  lda #0
  sta LINEBUF,y
  stx AX_POS                 ; save advanced cursor
  cpy #0
  beq run_next               ; blank line -> next
  jmp load_and_run
.alldone:
  stp


; ---- load the file named in LINEBUF and launch it ----
; A "W2X" magic prefix selects a multi-segment image (segments placed into
; their target banks by the loader); anything else is a flat binary loaded at
; $4000. Header reads use the OS ports (fixed, work from ROM); per-segment
; streaming into a bank runs from the lower-RAM stub (survives the switch).
load_and_run:
  lda #<LINEBUF
  ldx #>LINEBUF
  jsr os_open_read
  cmp #0
  bne .ok
  jsr clear_display
  lda #<msg_notfound
  ldx #>msg_notfound
  jsr display_string
  jmp run_next               ; skip the bad line, keep going
.ok:
  sta HANDLE
  sta P_SEL
  ; peek the 3-byte magic
  lda P_READ
  sta MAG0
  lda P_READ
  sta MAG1
  lda P_READ
  sta MAG2
  lda MAG0
  cmp #'W'
  bne .flat
  lda MAG1
  cmp #'2'
  bne .flat
  lda MAG2
  cmp #'X'
  beq .segmented

.flat:
  ; flat binary: the 3 peeked bytes are its first 3 bytes at $4000
  lda MAG0
  sta PROGRAM_LOAD+0
  lda MAG1
  sta PROGRAM_LOAD+1
  lda MAG2
  sta PROGRAM_LOAD+2
  lda #<(PROGRAM_LOAD+3)
  sta DESTL
  lda #>(PROGRAM_LOAD+3)
  sta DESTH
.frd:
  lda P_EOF
  bmi .launch
  lda P_READ
  sta (DESTL)
  inc DESTL
  bne .frd
  inc DESTH
  bra .frd

.segmented:
  lda P_READ                 ; segment count
  sta NSEG
.sloop:
  lda NSEG
  beq .launch
  dec NSEG
  lda P_READ                 ; descriptor: bank, addr_lo, addr_hi, len_lo, len_hi
  sta SBANK
  lda P_READ
  sta DESTL
  lda P_READ
  sta DESTH
  lda P_READ
  sta SLENL
  lda P_READ
  sta SLENH
  jsr SEG_STREAM_RAM         ; stream SLEN bytes into bank SBANK at DEST (runs in RAM)
  bra .sloop

.launch:
  lda HANDLE
  sta P_CLOSE
  jmp LAUNCH_RAM             ; switch to bank $01 and jmp $4000


; ---- read "autoexec" into AX_BUF; AX_LEN = byte count (0 if missing) ----
read_autoexec:
  stz AX_LEN
  lda #<autoexec_name
  ldx #>autoexec_name
  jsr os_open_read
  cmp #0
  beq .none
  sta HANDLE
  sta P_SEL
  ldy #0
.rd:
  lda P_EOF
  bmi .done
  lda P_READ
  sta AX_BUF,y
  iny
  bne .rd                    ; cap at 256 bytes
.done:
  sty AX_LEN
  lda HANDLE
  sta P_CLOSE
.none:
  rts


; ---- OS open-for-read: name ptr in A(lo)/X(hi) -> A = handle ----
os_open_read:
  sta NP
  stx NP+1
  sta P_NCLEAR
  ldy #0
.push:
  lda (NP),y
  beq .open
  sta P_NAME
  iny
  bne .push
.open:
  lda P_OPENR
  rts


; ---- stubs copied into fixed lower RAM (survive the bank switch) ----
launch_stub_src:
  lda #BANK_MASK
  trb BANK_PORT
  lda #BANK_START            ; $01 -> upper window = RAM bank 0; ROM out
  tsb BANK_PORT
  jmp PROGRAM_LOAD
launch_stub_end:

return_stub_src:
  lda #BANK_MASK
  trb BANK_PORT              ; config $00 -> ROM mapped back at $8000+
  jmp run_next
return_stub_end:

; Segment-stream stub: switch the window to bank SBANK, stream SLEN bytes from
; the OS read port into DEST, then restore config $00 (ROM) and return. Runs
; from lower RAM (copied to SEG_STREAM_RAM) so it survives the bank switch.
; Only relative branches + absolute/zp operands -> position-independent.
seg_stream_src:
  ldx SBANK
  lda #BANK_MASK
  trb BANK_PORT
  lda CFGTAB_RAM,x          ; PORTB config for logical bank SBANK
  tsb BANK_PORT
.sl:
  lda SLENL
  ora SLENH
  beq .sd
  lda P_READ
  sta (DESTL)
  inc DESTL
  bne .noih
  inc DESTH
.noih:
  lda SLENL
  bne .nodh
  dec SLENH
.nodh:
  dec SLENL
  bra .sl
.sd:
  lda #BANK_MASK
  trb BANK_PORT             ; config $00 -> ROM mapped back at $8000+
  rts
seg_stream_end:

cfgtab_src:
  .byte $01, $11, $12, $13, $14, $15, $16, $17   ; logical bank 0..7 -> PORTB cfg

banner:        asciiz "wendy2 monitor"
autoexec_name: asciiz "autoexec"
msg_notfound:  asciiz "prog not found"

  .include delay_routines.inc
  .include display_routines_4bit.inc
  .include display_string.inc

  ; ---- vectors ----
  .org $fffc
  .word reset
  .word $0000
