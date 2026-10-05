#!/usr/bin/env python3
"""Michael's ROM image, for the EEPROM: firmware/boards/michael/michael_rom.s assembled as the firmware manifest
records it (its esc flags), and only if it has the manifest's hash, so what goes on the chip is the recorded
build. The image isn't committed: the manifest's hash stands for it.

  python3 tools/michael_rom.py [--manifest PATH] [OUT]     (from anywhere; OUT defaults to
                                                           hardware/michael/michael_rom.bin)
  minipro -p AT28C256 -w hardware/michael/michael_rom.bin

Needs vasm6502_oldstyle on PATH (through firmware/vasm, which adds the include directories).
"""
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile

import firmware_manifest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SOURCE = 'firmware/boards/michael/michael_rom.s'
OUT = os.path.join(ROOT, 'hardware', 'michael', 'michael_rom.bin')
MANIFEST = os.path.join(ROOT, 'firmware', 'manifest.txt')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('out', nargs='?', default=OUT)
    parser.add_argument('--manifest', default=MANIFEST)
    args = parser.parse_args(argv)
    flags = firmware_manifest.BASE_FLAGS + dict(firmware_manifest.FLAG_SETS)['esc']
    recorded = firmware_manifest.read_manifest(args.manifest)[SOURCE][0].split('=', 1)[1]
    with tempfile.TemporaryDirectory() as tmp:
        built = os.path.join(tmp, 'michael_rom.bin')
        subprocess.run([os.path.join(ROOT, 'firmware', 'vasm'), *flags, '-o', built, SOURCE], cwd=ROOT, check=True)
        with open(built, 'rb') as f:
            image = f.read()
    if hashlib.sha256(image).hexdigest() != recorded:
        sys.exit(f'{SOURCE} builds an image the manifest ({args.manifest}) does not record: if the change is '
                 'intended, refresh it (python3 tools/firmware_manifest.py update --include-list '
                 'firmware/include-dirs) first')
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'wb') as f:
        f.write(image)
    print(f'{os.path.relpath(args.out)}: {SOURCE}, as the manifest records it')


if __name__ == '__main__':
    main()
