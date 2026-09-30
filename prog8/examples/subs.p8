; Phase 2.5: subroutine params + returns + asmsub.
; - asmsub bound directly to display_hex (display_hex.inc).
; - A user-defined sub that takes a ubyte and returns its doubled value.
; - A second user-defined sub that returns a uword (lo+hi pair via mkword-by-hand).

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

; Re-declare the existing display_hex (display_hex.inc, $XXXX) as an
; asmsub so we can call it as `hex(b)` instead of the builtin
; `txt.print_ub`. We don't actually know the runtime address of
; display_hex at compile time -- it's resolved by vasm at link time.
; To make this work, we use vasm by writing the call into a labelled
; helper. For now use txt.print_ub through the stdlib.

sub doubled(ubyte x) -> ubyte {
    return x + x
}

sub combine(ubyte lo, ubyte hi) -> uword {
    ; Build a uword as (hi << 8) | lo.
    uword w
    w = hi
    w = w << 8                    ; shift hi into high byte position
    ; OR in the low byte (lo widens to uword automatically).
    return w | lo
}

  sub start() {
    lcd.clear()
    txt.print("d=")
    txt.print_ub(doubled($07))    ; -> "0E"
    txt.print(" w=")
    txt.print_uw(combine($cd, $ab))  ; -> "ABCD"
  }
}
