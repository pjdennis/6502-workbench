# Writes rom.bin in the current directory: a tiny 32K ROM image from the 2020 Ben Eater-style
# Wendy (v1) breadboard (code at $8000, reset vector to it, rest NOP). Kept for history; current
# firmware is assembled with firmware/vasm.
code = bytearray([
  0xa9, 0xff,        # lda #$ff
  0x8d, 0x02, 0x60,  # sta $6002

  0xa9, 0x55,        # lda #$55
  0x8d, 0x00, 0x60,  # sta $6000

  0xa9, 0xaa,        # lda #$55
  0x8d, 0x00, 0x60,  # sta $6000

  0x4c, 0x05, 0x80   # jmp $8005
  ])

rom = code + bytearray([0xea] * (32768 - len(code)))

rom[0x7ffc] = 0x00
rom[0x7ffd] = 0x80

with open("rom.bin", "wb") as out_file:
  out_file.write(rom)
