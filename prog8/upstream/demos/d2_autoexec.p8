%output raw
%launcher none
%import textio
; D2 -- this program is loaded from the simulated SPI disk by the monitor ROM
; (named in 'autoexec'). It just shows it ran.
main {
    sub start() {
        txt.clear()
        txt.print("loaded by")
        txt.line2()
        txt.print("monitor+disk")
    }
}
