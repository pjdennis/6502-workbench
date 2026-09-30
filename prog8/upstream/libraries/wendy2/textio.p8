; Minimal txt I/O for the wendy2c HD44780 (4-bit) LCD.
;
; Direct port of display_routines_4bit.inc / display_update_routines_4bit.inc
; for the wendy2c wiring (base_config_wendy2c.inc):
;   VIA at $F000: PORTB=$F000  PORTA=$F001  DDRB=$F002  DDRA=$F003
;   data nibble = PORTA bits 7-4 ($F0);  RW=$08, RS=$01 on PORTA
;   E = $20 on PORTB ;  busy flag BF read on PORTA bit 7
;   DISPLAY_BITS_MASK = data|RW|RS = $F9
; The wendy2c boot ROM has already done the HD44780 4-bit init before
; handing control to the uploaded program, so this driver only writes.

%option no_symbol_prefixing, ignore_unused

txt {
    sub clear() {
        send_byte($01, 0)                   ; CMD_CLEAR_DISPLAY
    }

    sub home() {
        send_byte($02, 0)                   ; CMD_RETURN_HOME
    }

    sub line2() {
        send_byte($c0, 0)                   ; SET_DDRAM | $40 (second line)
    }

    sub chrout(ubyte char) {
        send_byte(char, $01)                ; RS=1 -> write to DDRAM (a glyph)
    }

    sub print(str s) {
        ubyte i = 0
        while s[i] != 0 {
            send_byte(s[i], $01)
            i++
        }
    }

    sub print_ub(ubyte value) {
        ; two hex chars, high nibble first
        chrout(hexdigit(value >> 4))
        chrout(hexdigit(value & $0f))
    }

    sub hexdigit(ubyte n) -> ubyte {
        if n < 10
            return n + '0'
        return n - 10 + 'A'
    }

    ; ---- the 4-bit nibble protocol ----
    ; value in A; rsflag in X ($01 for data/glyph, $00 for command).
    asmsub send_byte(ubyte value @A, ubyte rsflag @X) clobbers(A,X,Y) {
        %asm {{
            phy
            jsr  _wait              ; wait until not busy (preserves A? no -> save)
            pha
            asl  a                  ; lower nibble -> PORTA bits 7-4
            asl  a
            asl  a
            asl  a
            and  #$f0
            tay                     ; Y = second (low) nibble, positioned
            pla
            and  #$f0               ; A = first (high) nibble, already positioned
            tsb  $f001              ; PORTA: drive first nibble
            txa                     ; RS flag
            tsb  $f001              ; PORTA: set RS (or nothing for command)
            lda  #$20               ; E
            tsb  $f000              ; PORTB: E high
            trb  $f000              ; PORTB: E low (latch nibble)
            lda  #$f0
            trb  $f001              ; clear data lines
            tya
            tsb  $f001              ; PORTA: drive second nibble
            lda  #$20
            tsb  $f000              ; E high
            trb  $f000              ; E low (latch nibble)
            lda  #$f9               ; DISPLAY_BITS_MASK
            trb  $f001              ; clear data + RW + RS
            ply
            rts

_wait:
            pha                     ; preserve the byte to write across the poll
            phy                     ; (X/RS is untouched here -- poll reads via Y)
_busy:
            lda  #$f0
            trb  $f003              ; DDRA: data pins -> input
            lda  #$08               ; RW = read
            tsb  $f001
            lda  #$20               ; E
            tsb  $f000              ; E high
            ldy  $f001              ; read PORTA (BF in bit 7) into Y
            trb  $f000              ; E low (first nibble)
            tsb  $f000              ; E high
            trb  $f000              ; E low (second nibble, discarded)
            lda  #$f9
            trb  $f001              ; clear RW + data
            lda  #$f0
            tsb  $f003              ; DDRA: data pins -> output
            tya
            and  #$80               ; BF
            bne  _busy
            ply
            pla                     ; restore the byte to write
            rts
        }}
    }
}
