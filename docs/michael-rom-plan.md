# Plan: a new Michael ROM

Goal: a new EEPROM for Michael that
- takes uploads in a new format (below) that can fill RAM from `$0200` to `$3EFF` (15.25 KB instead of 13.5 KB), in one or more blocks;
- no longer reverses each byte's bits after an upload, because the uploader sends them already reversed;
- carries the LCD and keyboard services, at the same entry points as the emulator's environment (`toolchain/asm2/17/environment.asm`, `ENV_BASE = $F000`).

The asm2 editor then uploads alone, with about 4 KB of buffers instead of about 1 KB. The two-stage upload goes. The other boards stay as they are: every change is behind a flag or conditional assembly that only Michael turns on.

Branch: continue on `michael-editor` (or a new `michael-rom` from it).

## What the current loader does (firmware/lib/serial/upload_and_run.inc)

- It copies its receive handler to `$3F00`, where the ROM's IRQ vector points, and keeps its variables in `$00-$1F`.
- It builds a bit-reversal table at `$0200`, because the 6522's shift register takes bits most-significant first while the UART sends least-significant first.
- It receives the frame (a 2-byte length, the payload, then a 2-byte checksum) at `UPLOAD_TO`.
- It reverses every byte through the table, checks the checksum, copies the payload down 2 bytes onto `UPLOAD_TO`, and runs it.
- The ROM on the board uploads to `$0900`. The repo's `upload_and_run_eeprom_v2.s` still says `$2000`, so it isn't the source of that ROM.

## Design

**Upload format 2** (Michael only; the other boards keep format 1: length, payload, checksum).
- An upload is a header and one or more blocks, all 2-byte fields little-endian:

  ```
  header:  version (1) = 2           start address (2; $FFFF = don't run anything)
  block:   length (2)   load address (2)   checksum (2)   flags (1)   data (length bytes)
  flags:   bit 0 = more blocks follow   bit 1 = zero-fill (no data bytes: clear length bytes)
           other bits 0
  ```
- Every control byte comes before the data it describes. The loader stores the whole stream in order from `$01F6`, so the header and the first block's header fill `$01F6-$01FF` and the first block's data lands at `$0200`. One block can fill `$0200-$3EFF`, all of RAM below the receive handler's page, with no copying.
- **Rules**, which the uploader enforces and the loader checks:
  - blocks are in ascending address order, don't overlap, and start at `$0200` or above;
  - a block's data never moves down: its load address is at or above where its data sits in the stream;
  - every block ends by `$3F00`.
- **Checksums:** each block's checksum is the BSD sum of the stream from the end of the previous block (or the start of the upload) to the end of its data, less its own two checksum bytes. So it covers the header fields (and, for the first block, the upload's header) as well as the data.
- **Loader:**
  - The receive handler is unchanged; it only stores each byte and moves on. The loader's stack starts at `$01F5`, below the stream.
  - The main loop reads each header as its bytes arrive and checks it: a known version, the reserved flag bits 0, and the addresses within the rules. It checks each block's checksum in place once its data has arrived.
  - After the last block it moves the blocks up to their load addresses, last block first (each copied from the top down, since source and destination may overlap), then clears the zero-fill blocks.
  - Then it runs the start address, or with `$FFFF` shows what was loaded.
  - On any error it stops storing, turns off the receive interrupts and leaves the error on the LCD (bad version, bad block N, checksum N), with the LED lit, until reset.
- **Uploader** (`tools/upload/upload_frame.py`, `transfer.py`):
  - Builds format 2 from vasm's Intel HEX output (`-Fihex`), one block per contiguous run, or from a flat binary with a load address.
  - Merges blocks whose gap is too small for the data not to move down, filling the gap with zeros.
  - Never sends an empty last block: the last real block carries the end flag.
  - Sends every byte bit-reversed, because the 6522's shift register takes bits most-significant first. The loader then needs neither the reversal table (freeing `$0200`) nor the pass over the data.
  - `transfer.py --format=2` turns all this on; only Michael's scripts pass it, once the new ROM is on the board. `upload_frame.py` also writes an upload to a file, for the emulator's `--serial-input`.
- The IRQ vector stays at `$3F00` and the receive handler still runs from RAM there, since its cycle timing is critical at 57600 baud.
- The new loader is a new include, `upload_v2.inc`, sharing `serial_receive_timing.inc` and `serial_receive_interrupt.inc` with `upload_and_run.inc`, which is left alone.

**Services in the ROM.**
- The vector table sits at `$F006-$F068`, the offsets of `17/environment.asm`, so a program built for the emulator's environment calls the same addresses on Michael. The asm2 editor's `define:michael` then needs no vector changes at all, and `editor/michael_environment.asm` goes.
- The entries:
  - `write_b` and the `scr_*` calls draw on the LCD.
  - `con_read`, `con_ready` and `con_flush` handle keys and redrawing.
  - `term_rows` and `term_cols` return 4 and 20.
  - `argc` and the file calls return "none".
  - `exit` jumps back to the loader through the reset vector (today it stops the CPU).
- The code is the `lcd_screen.inc`, `keyboard_keys.inc` and keyboard-driver code the editor runs today, moved into ROM. The only code change is that the "started" flag moves to RAM.
- **Michael-only vectors after `$F068`**, for other programs:
  - `services_start`, to start the LCD and keyboard without calling `argc`;
  - `kbd_get_scancode`, for raw scan codes;
  - `lcd_command` and `lcd_data`;
  - `delay_ms`.
- A new `firmware/boards/michael/michael_rom_vectors.inc` names all the vectors for vasm programs. The editor keeps using `17/environment.asm`.
- **Services' RAM** stays where it is today (`michael_editor_layout.inc`):
  - zero page `$F0-$FF`;
  - `$3F00-$3F8F`: the IRQ slot (the services write a `jmp` to their keyboard handler there when they start), the key ring and the screen copy.
  - `$3F90-$3FFF` stays free for programs.
- **ROM source:** a new `firmware/boards/michael/michael_rom.s` (loader, services, vector table, reset and IRQ vectors), built into `michael_rom.bin`. The loader and the services share one set of LCD routines. `upload_and_run_eeprom_v2.s` is left alone, since it doesn't match any board.

**The editor on the new ROM.**
- `define:michael` keeps its memory map but moves the origin to `$0200`.
- The code runs `$0200-$2E1E`, and the buffers go above it up to `$3EFF`, about 4 KB. Roughly:
  - text: 2.5 KB;
  - line table: 512 bytes (255 lines);
  - yank: 512 bytes;
  - undo: 256 bytes;
  - batch, marks, search, file name and command line: in page 1 below the stack, and in `$3F90`.
- `editor/michael_image.py` becomes a plain build, since there are no services to add, and `editor-michael-upload.sh` a single upload.

## Phases (each test-first, in the emulator before the board)

1. **Uploader.**
   - Format 2, the packer, bit reversal and writing an upload to a file, in `upload_frame.py`, with unit tests.
   - `transfer.py --format=2`.
   - The other boards' scripts are unchanged; the tests check that.
2. **Loader.**
   - `upload_v2.inc`, run first as a RAM program in the emulator (loaded with `--load`, the upload fed by `--serial-input`): single and multiple blocks, zero-fill, and each error.
   - Every existing loader and ROM binary stays byte-identical (the firmware manifest).
3. **The ROM.**
   - `michael_rom.s`: the loader at reset, the services and the vector table.
   - The Michael machine boots from a ROM image: with `--rom` and no `--load`, nothing goes into RAM.
   - A `michael_goldens.sh` case boots `michael_rom.bin` and uploads a program over the serial line.
   - A test that the ROM's vector table matches `17/environment.asm`.
4. **Editor on the ROM.**
   - The editor's origin and memory map for Michael, and `michael_environment.asm` removed.
   - `michael_tests.py` boots the ROM, uploads the editor over the serial line, and runs the existing scripts, differential tests, live test and stack check against it.
5. **The new ROM image.** Committed, in the manifest and handed over for programming (below). When you confirm it runs on the board:
   - `base_config_v2.inc` changes to `PROGRAM_LOAD_ADDRESS = $0200`, since the config follows the ROM on the board;
   - `compile_and_upload_michael.sh` assembles to Intel HEX and passes `--format=2`.
6. **Programs with data at `$0200`-`$08FF`.** These would be overwritten by their own code once it loads at `$0200`. Their buffers move to the top of RAM below `$3F00`, as the editor's do:
   - `michael_keyboard_new.s`, `michael_keyboard_show_names.s` and `michael_keyboard_diag.s` (the tests in `tools/tests/test_michael_keyboard.py` cover these three);
   - `michael_graphic_keyboard.s` and `michael_graphic_prompt.s`, `michael_graphic_prompt_template.s`, `michael_graphic_bf.s`.

   The `.org $2000` programs predate the current ROM and are left as they are. BBC BASIC has its own loader and memory map and is also left alone.
7. **Cleanup of the two-stage upload** (it stays in the history). Remove:
   - `firmware/programs/michael/michael_second_stage_loader.s` and its manifest entry;
   - `tools/upload/upload_michael_big.sh` and its README row;
   - `MichaelBigUploadTest` in `tools/tests/test_upload_scripts.py`;
   - the three second-stage tests in `michael_tests.py`;
   - the RAM services build (`michael_editor_services.s`), once the ROM carries them. Its tests (`test_michael_editor_services.py`) move to the ROM image.

   Keep:
   - the `serial_receive*.inc` split, which the ROM uses;
   - `--serial-input` for the Michael machine;
   - `lcd_screen.inc` and `keyboard_keys.inc`, which the ROM includes.

## Programming the EEPROM

Back up the one on the board first, since its source isn't in the repo:

```
minipro -p AT28C256 -r michael-rom-backup.bin
```

Then, when I tell you the new image is ready:

```
minipro -p AT28C256 -w firmware/boards/michael/michael_rom.bin
```

This is the same command `tools/upload/compile_and_program.sh` uses. If the chip's write protection is on, add `--no-write-protect` (as for the Wendy 2 PLD in `hardware/wendy2/README.md`). To go back, write the backup the same way.

## Other suggestions

- **ROM identity:** a version string at a fixed address, e.g. `$FFE0` "MICHAEL ROM 3". `michael_show_vectors.s` shows it, and a program or upload script can check it.
- **Faster boot to the loader:** the reset path shows "Ready" straight away. Starting the LCD and keyboard waits until a program asks for them, so the loader's timing and messages stay as they are.
- **Uploads that don't run:** with start address `$FFFF` the loader only loads. A data upload can then go to one place, followed by a program that uses it.
- **The editor in ROM, later:** at about 12 KB the editor fits beside the loader and services in the 32 KB EEPROM. It would start from a menu key or a service call, leaving all 15 KB of RAM for text. That only makes sense once the editor changes rarely, since every change means reprogramming the EEPROM. For now it stays an upload.
- **Service calls for other programs:** with the services in ROM, the keyboard programs (`michael_keyboard_new.s` and the rest) could drop their own copies of the driver and LCD routines and call the ROM. That would make them much smaller. It's optional, and they'd no longer run on the old ROM.
- **Upload speed:** 57600 baud is about the limit. At 2 MHz a half bit is about 17 cycles, and the handler's timing is already tuned close to it, so 115200 isn't practical without a faster clock.
