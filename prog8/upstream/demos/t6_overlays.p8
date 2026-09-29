%output raw
%launcher none
%import textio
%import banking
%import os
; T6 -- load code overlays from the SPI disk into MULTIPLE banks, then execute
; across them (storage-driven model: the surrounding environment supplies the
; banked code as files; the program streams each file into its bank, like the
; C128 SETBNK+LOAD / cx16 LOAD-into-HIRAM pattern). This program is itself
; loaded from disk by the monitor (autoexec).
;
; Each overlay file is a routine (position-correct for $A000):
;   inc $0200 ; lda #'a'/'b'/'c' ; rts
main {
    sub start() {
        txt.clear()
        @($0200) = 0                        ; shared counter in fixed lower RAM
        load_into_bank("ov1", 1)
        load_into_bank("ov2", 2)
        load_into_bank("ov3", 3)
        txt.chrout(banking.bank_call(1, $a000))   ; execute across the banks
        txt.chrout(banking.bank_call(2, $a000))
        txt.chrout(banking.bank_call(3, $a000))
        txt.print(" n=")
        txt.chrout($30 + @($0200))
    }

    ; stream a disk file straight into bank `bank` at $A000 (LOAD-into-bank)
    sub load_into_bank(str name, ubyte bank) {
        ubyte h = os.openfile(name)
        if h == 0
            return
        os.select(h)
        banking.set_upper_bank(bank)        ; hold the bank in while we stream
        uword i = 0
        while not os.at_eof() {
            @($a000 + i) = os.readbyte()
            i++
        }
        os.closefile()
    }
}
