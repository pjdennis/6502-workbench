%output raw
%launcher none
%import textio
%import os
; D1 -- read a file from the simulated SPI disk and print it to the LCD.
main {
    sub start() {
        txt.clear()
        ubyte h = os.openfile("greeting")
        if h == 0 {
            txt.print("no file")
            return
        }
        os.select(h)
        while not os.at_eof() {
            txt.chrout(os.readbyte())
        }
        os.closefile()
    }
}
