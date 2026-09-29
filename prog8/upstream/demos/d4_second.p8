%output raw
%launcher none
%import textio
; D4 program B: run by the monitor AFTER A returned; writes line 2.
main {
    sub start() {
        txt.line2()
        txt.print("second runs")
    }
}
