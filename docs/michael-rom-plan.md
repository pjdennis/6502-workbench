# Plan: a new Michael ROM

Goal: a new EEPROM for Michael that
- takes uploads from `$0200` (about 15.2 KB instead of 13.5 KB);
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

**Bits reversed by the uploader.**
- `upload_frame.py` gains `reverse_bits(frame)`, and `transfer.py` gains `--reverse-bits`, which sends every byte of the frame reversed.
- Only `compile_and_upload_michael.sh` passes it.
- In the loader, `.ifdef UPLOAD_BITS_REVERSED` drops `build_translate` and `translate_data`, and reads the length directly. Only the new Michael ROM sets it. The table's page at `$0200` is then free.

**Uploads from `$0200`, with no copy.**
- With `.ifdef UPLOAD_LENGTH_BELOW` (Michael only), the loader starts its stack at `$01FB` and receives from `$01FE`.
- The length lands in `$01FE-$01FF`, the payload at `$0200`, where it runs, and the checksum just after it.
- A frame must end below the handler's page (`$3F00`): a payload of up to 15,614 bytes (`$0200-$3EFD`). A longer one gets "Too long" on the LCD rather than being received.
- `$0200` is the lowest a program can start: page 0 is zero page, page 1 the stack.
- The IRQ vector stays at `$3F00`, and the handler still runs from RAM there. Its cycle timing is critical at 57600 baud, so it doesn't change.

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
   - `reverse_bits` and `--reverse-bits`, with unit tests in `tools/tests` (`test_upload_frame.py`, `test_upload_scripts.py`).
   - The other boards' scripts are unchanged; the tests check that.
2. **Loader options.**
   - `UPLOAD_BITS_REVERSED` and `UPLOAD_LENGTH_BELOW` in `upload_and_run.inc`.
   - Every existing loader and ROM binary must stay byte-identical (the firmware manifest).
   - The emulator's Michael machine gets an option to send `--serial-input` bytes reversed, so tests can run the real ROM.
3. **The ROM.**
   - `michael_rom.s` and a `michael_goldens.sh` case: boot `--rom michael_rom.bin`, upload a program through the serial line, and check the LCD.
   - A test that the ROM's vector table matches `17/environment.asm`, like the one comparing `michael_environment.asm` today.
4. **Editor on the ROM.**
   - The editor's origin and memory map for Michael, and `michael_environment.asm` removed.
   - `michael_tests.py` boots the ROM, uploads the editor over the serial line, and runs the existing scripts, differential tests, live test and stack check against it.
   - `--load` without `--rom` stays for other tests.
5. **The new ROM image.** Committed, in the manifest and handed over for programming (below). When you confirm it runs on the board:
   - `base_config_v2.inc` changes to `PROGRAM_LOAD_ADDRESS = $0200`, since the config follows the ROM on the board;
   - `compile_and_upload_michael.sh` passes `--reverse-bits`.
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
- **The editor in ROM, later:** at about 12 KB the editor fits beside the loader and services in the 32 KB EEPROM. It would start from a menu key or a service call, leaving all 15 KB of RAM for text. That only makes sense once the editor changes rarely, since every change means reprogramming the EEPROM. For now it stays an upload.
- **Service calls for other programs:** with the services in ROM, the keyboard programs (`michael_keyboard_new.s` and the rest) could drop their own copies of the driver and LCD routines and call the ROM. That would make them much smaller. It's optional, and they'd no longer run on the old ROM.
- **Upload speed:** 57600 baud is about the limit. At 2 MHz a half bit is about 17 cycles, and the handler's timing is already tuned close to it, so 115200 isn't practical without a faster clock.
