  .include base_config_v2.inc

ORIGIN    = PROGRAM_LOAD_ADDRESS
UPLOAD_TO = $3000

BPS_HUNDREDS = 576 ; 57600 bps

  .include upload_and_run.inc
  .include initialize_machine_v2.inc
  .include display_routines_8bit.inc

origin_message: asciiz 'RAM'
