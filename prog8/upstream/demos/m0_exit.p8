%output raw
%launcher none
; M0 -- minimal target smoke test: compiles, boots, runs, halts (STP).
main {
    sub start() {
        ; nothing -- falls through to cleanup_at_exit (STP); emulator dumps LCD
    }
}
