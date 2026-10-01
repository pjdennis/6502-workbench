# serial

The bit-banged serial upload loaders: the 6522 shift register (CB2), timer 2 and an interrupt handler receive bytes into RAM. The sender is `tools/upload/transfer.py`; the formats are in `tools/upload/upload_frame.py`.

- `upload_and_run.inc`: format 1 (length, payload, checksum), included by every board's `upload_and_run_{ram,eeprom}_*.s`. Needs `BPS_HUNDREDS` and `CLOCK_FREQ_KHZ`.
- `upload_v3.inc`: format 3 (table of entries then data, for Michael's ROM; see `docs/michael-upload-format-3-plan.md`).
- `serial_receive_interrupt.inc`: the interrupt-driven byte receiver, included by both loaders and copied to `INTERRUPT_ROUTINE`. Its timing counts cycles from the interrupt, so it must run where the IRQ vector points.
- `serial_receive_timing.inc`: the bit-timing constants, included by `upload_and_run.inc` and `michael_rom.s`.
- `serial_receive.inc`: undoes the received bytes' bit reversal and checks the frame's checksum; used only by `upload_and_run.inc` (format 3 has its own in `upload_v3.inc`).
