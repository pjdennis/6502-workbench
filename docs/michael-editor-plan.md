# Plan: the asm2 editor on Michael

Goal: run `toolchain/asm2/editor` on Michael (the v2 board), with the 20x4 LCD as the screen and the PS/2 keyboard board (`Bidirectional PS2 Keyboard Interface Schematic v1.0.pdf`) as input. For now everything runs from RAM. Load and save are left out: the editor starts with an unnamed empty file and `openout` fails, so `:w` shows "Can't open file for writing". The editor changes as little as possible. The `emulator/` gets a Michael machine so all of this can be tested.

Branch: `michael-editor`, from `editor-size-series` with GitHub `main` merged in.

## Findings

**Editor I/O.** The console build does all output through `write_b` as ANSI sequences:
- cursor position (`ESC[r;cH`), `ESC[K`, `ESC[2J`, `ESC[?25l/h`, `ESC[7m`/`ESC[0m`;
- scroll regions (`ESC[t;br`, `ESC[r`);
- insert and delete characters (`ESC[n@`, `ESC[nP`);
- scroll up and down (`ESC[nS`, `ESC[nT`).

It reads input through `con_read`, `con_ready` and `wait_ready`, and recognises a lone Esc by a 100 ms timeout. It reads the screen size at run time from `term_rows`/`term_cols`.

At 4 rows by 20 columns the editor wraps text lines itself. The status line (`[No Name] [+] - INSERT - 2,7 /2`, about 31 characters) is longer than 20 characters and relies on the terminal to clip it, so the Michael console clips at column 20 and never wraps. A shorter status line for narrow screens is an optional later editor change.

**Saving.** Nothing in the editor stops `:w` on "[No Name]". On Michael `openout` returns 0, so no editor change is needed.

**Memory.** Michael has 16 KB of RAM ($0000-$3FFF). The IRQ vector points at $3F00, and the ROM loader receives uploads at $0900, so it can take $0900-$3EFF (13,824 bytes).

| Code | Size |
|---|---|
| editor (console build) | 12,108 bytes |
| keyboard driver and tables | ~1,280 bytes (measured) |
| LCD routines | ~300 bytes (measured) |
| ANSI and key-translation layer | ~750 bytes (estimate) |
| total | ~14.4 KB |

That leaves about 0.7-1 KB for all the editor's buffers. Today they are hard-coded at $D600-$EFFF.

**Emulator.** `emulator/` has VIA and HD44780 models, but the LCD is wired for wendy2c (4-bit, 16x2). There is no Michael machine, no CA2 input and no Port B inputs. `tools/michael_keyboard_sim.c` is the reference for the keyboard board's behaviour. Its tests move onto the emulator and the simulator is then removed.

## Memory layout (RAM phase)

| Range | Contents |
|---|---|
| $00-$DF | Editor zero page. The editor clears all of zero page at start-up. |
| $E0-$FF | Services zero page, initialised on the first service call (`argc`, which comes after the clear). |
| $0100 / $0200 / $0300 | Stack / `FNAME_BUF` / `CMD_BUF` (unchanged) |
| $0400-$08FF | Services part A: jump table at a fixed address, keyboard driver and tables |
| $0900-~$384B | Editor code, origin $0900: the loader's address, so the same image works after the services move to ROM |
| ~$3850-$3EFF | Services part B (LCD, ANSI engine, key translation, 80-byte screen copy), then the editor's small buffers |
| $3F00-$3FFF | Keyboard IRQ handler and key ring buffer |

## Phases

Each step is test-first: the test and the code that makes it pass go in the same commit, and refactors are separate commits.

### 1. Michael machine in `emulator/`
- **1a.** Refactor so the LCD's wiring and geometry are set per machine: bus width, which port and bits carry E, RW and RS, and the data lines. Wendy2c output must stay identical.
- **1b.** `--machine michael`:
  - RAM $0000-$3FFF, VIA $6000-$7FFF, ROM $8000-$FFFF.
  - Programs load with `--load`. A built-in vector stub points IRQ at $3F00, and `--rom` loads a real image.
  - An 8-bit LCD on Port B with E=PA7, RW=PA6, RS=PA5, set with `--lcd-panel 20x4`. Busy-flag and DDRAM reads work.
  - First test: `hello_michael_test-20x4.s`.
- **1c.** VIA: a CA2 negative-edge interrupt input, and Port B input pins driven by an external device.
- **1d.** Keyboard board model in `chips/`:
  - SOLB sends a command, and the keyboard answers with ACK or RESEND frames.
  - CA2 edges come at the start and end of each frame.
  - While SOEB is low, Port B carries the inverted byte.
  - The simulator's "bad LCD write" check becomes an emulator diagnostic.
  - `tools/tests/test_michael_keyboard.py` moves onto the emulator, including its fault cases, and `tools/michael_keyboard_sim.c` is deleted.
- **1e.** Key input:
  - A host-key to PS/2 set 2 scan code encoder: make and break codes, E0 prefixes, Shift, Ctrl.
  - `--keys FILE` takes the editor's key vocabulary (ASCII plus ANSI key sequences), so the editor's key scripts can be reused.
  - `--live` maps terminal keys and draws the LCD.

### 2. Editor build configuration (the only editor change)
- **2a.** Refactor with no change to the output:
  - `17/environment.asm` defines each vector as `ENV_BASE + offset`.
  - The buffer addresses in `buffer.asm`, `yank.asm`, `mark.asm`, `search.asm` and `undo_state.asm` move into one memory-map block in `editor.asm`. `MAX_LINES`, `YANK_LIMIT` and the other limits are derived from it.
  - Check: every build is byte-identical to the stable binaries.
- **2b.** `define:michael`:
  - Selects the Michael `ENV_BASE`, origin $0900 and the small buffer layout.
  - Adds a build-time check that code and buffers end below the services area.
  - Keeps the page alignment that `TEXT_BUF` and `YANK_BUF` rely on.
  - `editor_tests.py` builds `editor_michael.out`.

### 3. Michael console services (vasm, ROM-ready: no self-modifying code, code and data kept apart)
- **Screen:**
  - A 20x4 screen copy with dirty-row flags.
  - An ANSI parser for ESC and CSI with up to two parameters and the `?` prefix, handling `H K J m r @ P S T` and `?25h/l`.
  - Clip at column 20 and never wrap; reverse video is ignored.
  - `~` and `\` are shown through the custom characters in `extend_character_set.inc`.
  - `con_flush`, and any wait for input, writes the dirty rows and places the LCD cursor.
- **Keyboard:**
  - An opt-in driver option so `keyboard_get_char` also returns KEY_* codes with the modifier state. Existing programs and firmware hashes stay unchanged.
  - Enter (LF) becomes CR, Backspace becomes $08, Esc becomes $1B, and Ctrl+letter becomes the control code.
  - Arrows, Home, End, PgUp, PgDn, Delete and Ctrl+Left/Right become the ANSI sequences the editor decodes. Each sequence is queued whole, so the Esc timeout still works.
- **Services:**
  - `term_rows`=4, `term_cols`=20, `argc`=0.
  - `open` and `openout` return 0; `close` and `read` are stubs.
  - `exit` jumps to the ROM reset, back to the loader.
  - `wait_ready` times out using VIA timer T1, polled.
- **Tests:**
  - Emulator harness programs check LCD frames for given ANSI input, and the bytes produced for given scan codes.
  - A differential test replays editor output recorded at 4x20 through the Michael console and compares the LCD with `AnsiScreen(4, 20)`, clipped at column 20.

### 4. End to end in the emulator
- Load the services and `editor_michael.out` into the Michael machine.
- Key scripts check LCD frames: insert, Esc, motions, scrolling in the 3-row text area, and `:w` failing.
- One test goes through the relocator (below) to check the board's start-up path.
- Add a `michael` suite to `tools/check_all.sh`, and a launcher for live use.

### 5. Onto the board
A small general relocator sits at the start of an upload image:
- It works through a table of source, destination and length entries, copying down or up as each block needs.
- It then jumps to a start address or returns to the ROM loader.
- Its memory is later reused by the editor's buffers.

The editor stays at $0900, so it is uploaded exactly as assembled.

While the code is larger than the 13.8 KB upload window, one script sends two uploads back to back:
1. The relocator and the services. The relocator places parts A and B and returns to the loader, which only touches $00-$1F, $0200-$02FF and $3F00.
2. The editor, sent with `--noreset`.

If the sizes come down enough, from more editor size work or a trimmed keyboard driver, the script joins the two images into one upload. No ROM change is needed.

## Open points
- `upload_and_run_eeprom_v2.s` hard-codes `UPLOAD_TO = $2000`, but `base_config_v2.inc` has $0900 "to match the current rom". This plan assumes the board runs $0900 with IRQ at $3F00.
- The buffers in the RAM phase are tiny: about 700 bytes of text, around 128 lines, and small yank and undo areas. They grow by about 2.3 KB when the services move to ROM.
