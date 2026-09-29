%output raw
%launcher none
%import textio
; D4 program A: clears and writes line 1, then returns to the monitor.
main {
    sub start() {
        txt.clear()
        txt.print("first runs")
    }
}
