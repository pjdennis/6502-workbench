; Where the asm2 editor and its services sit in Michael's RAM, for both
; sides: firmware/programs/michael/michael_editor_services.s (vasm) and the
; editor's define:michael build (asm2, which includes this file by path).
; Plain "NAME = $value" lines only, so both assemblers read it.

; The services' vector table: ENV_BASE + $06 on, as in
; toolchain/asm2/17/environment.asm. The services start at ENV_BASE + $06
; and end below the interrupt page.
MICHAEL_ENV_BASE = $34fa
