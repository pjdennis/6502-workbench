; OS-call file I/O for the wendy2c "disk" (simulated SPI mass storage).
;
; Thin wrappers over the emulator's $F800-$F80F port block (installed when the
; emulator is run with --disk DIR). Filenames are pushed byte-by-byte into the
; chip; handles are small integers. The ports live in the fixed high-RAM
; window, so these calls work from any bank. See WENDY2_DISK_BOOT_DESIGN.md.

%option no_symbol_prefixing, ignore_unused

os {
    const uword P_NAME   = $f800     ; W: append filename byte
    const uword P_NCLEAR = $f801     ; W: clear filename buffer
    const uword P_OPENR  = $f802     ; R: open-for-read  -> handle
    const uword P_OPENW  = $f803     ; R: open-for-write -> handle
    const uword P_SEL    = $f804     ; W: select current handle
    const uword P_READ   = $f805     ; R: read byte from current handle
    const uword P_EOF    = $f806     ; R: EOF of current handle (bit7)
    const uword P_WRITE  = $f807     ; W: write byte to current handle
    const uword P_CLOSE  = $f808     ; W: close current handle
    const uword P_POWER  = $f80f     ; W: power off / halt (code)

    sub setname(str name) {
        @(P_NCLEAR) = 0
        ubyte i = 0
        while name[i] != 0 {
            @(P_NAME) = name[i]
            i++
        }
    }

    ; open a disk file for reading; returns a handle (0 = not found/fail)
    sub openfile(str name) -> ubyte {
        setname(name)
        return @(P_OPENR)
    }

    ; create/truncate a disk file for writing; returns a handle (0 = fail)
    sub createfile(str name) -> ubyte {
        setname(name)
        return @(P_OPENW)
    }

    sub select(ubyte handle) {
        @(P_SEL) = handle
    }

    sub readbyte() -> ubyte {
        return @(P_READ)
    }

    sub at_eof() -> bool {
        return (@(P_EOF) & $80) != 0
    }

    sub writebyte(ubyte b) {
        @(P_WRITE) = b
    }

    sub closefile() {
        @(P_CLOSE) = 0
    }

    sub poweroff(ubyte code) {
        @(P_POWER) = code
    }
}
