#!/usr/bin/env python3
"""Pack a wendy2 multi-segment program image (.w2x) for the monitor loader.

A .w2x image is:
    "W2X"                      magic (3 bytes)
    nseg                       segment count (1 byte)
    nseg x [ bank, addr_lo, addr_hi, len_lo, len_hi, <data...> ]
where bank 0 = the fixed lower-32K RAM (the main program, typically @ $4000)
and bank 1..7 = an upper RAM bank (code/data @ a window address $8000-$EFFF).
The monitor (wendy2c_monitor.s) streams each segment into its target bank,
then launches bank 0 at $4000. See WENDY2_DISK_BOOT_DESIGN.md.

Usage:
    wendy2_pack.py -o app.w2x MAIN.bin [FILE@BANK@HEXADDR ...]

  MAIN.bin              -> segment bank 0 @ $4000 (the resident program)
  ov.bin@1@A000         -> segment bank 1 @ $A000 (a banked overlay)

Example:
    wendy2_pack.py -o app.w2x main.bin r1.bin@1@A000 r2.bin@2@A000
"""
import sys


def seg_bytes(bank: int, addr: int, data: bytes) -> bytes:
    if not (0 <= bank <= 7):
        sys.exit(f"bank out of range (0..7): {bank}")
    if len(data) > 0xFFFF:
        sys.exit("segment too large")
    return bytes([bank, addr & 0xFF, addr >> 8, len(data) & 0xFF, len(data) >> 8]) + data


def main(argv):
    if len(argv) < 4 or argv[1] != "-o":
        sys.exit(__doc__)
    out = argv[2]
    main_bin = argv[3]
    segs = [seg_bytes(0, 0x4000, open(main_bin, "rb").read())]
    for spec in argv[4:]:
        try:
            path, bank, addr = spec.split("@")
            segs.append(seg_bytes(int(bank), int(addr, 16), open(path, "rb").read()))
        except ValueError:
            sys.exit(f"bad segment spec (want FILE@BANK@HEXADDR): {spec}")
    if len(segs) > 255:
        sys.exit("too many segments")
    img = b"W2X" + bytes([len(segs)]) + b"".join(segs)
    open(out, "wb").write(img)
    print(f"wrote {out}: {len(segs)} segments, {len(img)} bytes")


if __name__ == "__main__":
    main(sys.argv)
