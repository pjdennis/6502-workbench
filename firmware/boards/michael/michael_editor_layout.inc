; How the editor and the Michael ROM's services (michael_services.inc) share Michael's RAM,
; for both sides: the ROM (vasm) and the editor's define:michael build (built by asm17, which includes this
; file by path, from editor/memory_map.asm).
; Plain "NAME = $VALUE" lines only, with upper-case hex, so both assemblers read it.

; The services keep their RAM at the start of the interrupt page ($3F00);
; from here to the end of RAM is the editor's
MICHAEL_EDITOR_SPARE = $3F90
