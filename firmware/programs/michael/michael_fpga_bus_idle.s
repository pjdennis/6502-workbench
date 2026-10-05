; Leaves Michael quiet on the FPGA bus: E (PA2) an output, held low, and nothing else, with interrupts off.
; The FPGA bus checks (hardware/michael/fpga/bus-check/) upload it before loading their design, so that a
; program still running from before, or the ROM, can't make transfers that the design then counts.
  .include base_config_v2.inc

  .org PROGRAM_LOAD_ADDRESS
start:
  sei
  jsr fb_initialize
.forever:
  bra .forever

  .include fpga_bus.inc
