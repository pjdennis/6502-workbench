; The Michael services (michael_services.inc) built for RAM, at MICHAEL_ENV_BASE, to upload
; with the asm2 editor's define:direct_io, define:michael build (michael_editor_layout.inc).
; exit stops the CPU (STP): press reset to get back to the loader.

  .include base_config_v2.inc
  .include michael_editor_layout.inc

SVC_BASE         = MICHAEL_ENV_BASE
SERVICES_STARTED = services_started
SERVICES_EXIT    = services_stop

  .org MICHAEL_ENV_BASE + $06
  .include michael_services.inc

services_started:
  .byte 0

services_stop:
  stp

services_end:

  .if services_end > INTERRUPT_ROUTINE
  fail "The services run into the interrupt page"
  .endif
