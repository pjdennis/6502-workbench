%output raw
%launcher none
main {
    sub start() {
        ubyte dst = openout(argv(1))        ; open output file (argv[1])
        writeb('H', dst)
        writeb('I', dst)
        writeb($0a, dst)
        close(dst)
    }
    ; --- emulator $F006+ syscall stubs (same ABI p1.p8 uses) ---
    asmsub argv(ubyte i @A) -> uword @AY {
        %asm {{
            jsr  $f01e          ; A=index -> A=lo, X=hi
            pha
            txa
            tay
            pla
            rts
        }}
    }
    asmsub openout(uword fn @AY) -> ubyte @A {
        %asm {{
            pha                 ; save lo
            tya
            tax                 ; X = hi
            pla                 ; A = lo
            jsr  $f021          ; -> handle in A
            rts
        }}
    }
    asmsub writeb(ubyte b @A, ubyte handle @X) {
        %asm {{
            jsr  $f024          ; A=byte, X=handle
            rts
        }}
    }
    asmsub close(ubyte handle @A) {
        %asm {{
            jsr  $f015
            rts
        }}
    }
}
