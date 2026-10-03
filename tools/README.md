# Tools

Host-side tools. Run them from the repository root unless noted.

| Path | What it does |
|---|---|
| `build_all.sh` | Builds the main tools, so the scripts that use them work (e.g. `editor/bin/editor.sh` and `editor-michael-upload.sh`): `emulator`, `asm` (the chain up to asm17, via `asmtestgen.sh`) and `editor` (its stable builds, written once its tests pass), all or the ones named. About 30 seconds. |
| `check_all.sh` | Runs every regression suite: `firmware`, `asm`, `editor`, `emulator`, `prog8` (all, or the ones named). CI runs the same suites. |
| `firmware_manifest.py` | Firmware regression check: assembles every program and compares hashes with `firmware/manifest.txt` (see `firmware/README.md`). Tests in `tests/`. |
| `upload/upload_frame.py [--load-address=HEX] [--start=HEX] FILE OUT` | The upload formats (see its docstring). As a command, writes FILE (binary, or S-records `.s19`) as a format 3 upload, as it goes on the wire, e.g. for the emulator's `--serial-input`. |
| `upload/transfer.py` | Sends a binary to a board's serial loader: length, payload and checksum (`upload_frame.py`), with a DTR reset pulse first. Options: `--port`, `--baudrate`, `--noreset`, `--stopbits`, `--wait` (return only once the upload has had time to send), `--format=3` (Michael's format: a table of entries, then their data; `--load-address` for a binary, default `2000`, and `--start`; an S-record `.s19` file gives its own addresses and start address). Auto-detects a single USB serial port, skipping those matched by a pattern in `upload/ignored-serial-ports.txt` (e.g. Digilent boards). Goes through `serial_daemon.py`, starting it on first use; `--direct` opens the port itself instead (and always waits), and `--daemon status` / `--daemon stop` report on or stop the daemon. Needs `pyserial`. |
| `upload/serial_daemon.py` | Holds the USB serial port open for `transfer.py`. On Linux, opening the port asserts DTR, which resets Wendy 2, so a `--noreset` upload would reach a freshly reset ROM loader. One daemon per user, shared by every clone, on the socket `$XDG_RUNTIME_DIR/6502-serial-daemon.sock` (override with `SERIAL_DAEMON_SOCKET`); its log is the socket path plus `.log`. It opens the port on the first upload and exits when the adapter is unplugged, rather than wait and grab whatever appears next (the next upload starts a new daemon). It refuses the first `--noreset` upload after it opens the port because that open reset the board. After updating it, run `transfer.py --daemon stop`; the next upload starts the new version. Restarting the daemon also resets the board. |
| `upload/compile_and_upload_<board>.sh [--noreset] <program.s>` | Assembles with `firmware/vasm` to `a.out`, then runs `transfer.py` with the board's baud rate, through `compile_and_upload.sh`. Michael's assembles to S-records (`a.s19`, `compile_and_upload.sh --srec`, vasm `-Fsrec -exec`) and sends them in format 3, so the program loads at its `.org` and starts at its `start` label, which it must have (a label: vasm writes 0 for an equate, which the tools refuse). Other `transfer.py` options (e.g. `--wait`, `--port=DEVICE`) are passed on. Wendy has no DTR reset, so `compile_and_upload_wendy.sh` always uses `--direct --noreset`. |
| `upload/compile_and_program.sh <program.s>` | Assembles and burns an AT28C256 EEPROM with `minipro`. |
| `upload/test_dtr.py` | Toggles DTR to test the reset line. |
| `lcd-ocr/` | Reads the Wendy 2 LCD through a webcam: `lcd_read`, `lcd_ocr.py`, `lcd_inspect.py` and `calibrate.py`. `apply_font_to_emulator.py` copies the captured font into the emulator. Uses the local, untracked `snap.sh` and `lcd_calibration.json` at the repository root. |
| `reorg/create_tags.sh` | Creates and pushes the history tags: milestones (`reorg/milestones.txt`), `archive/<branch>` tags for the old repository's branches (`reorg/archive-tips.txt`), and `reorg/before`/`reorg/after`. A dry run by default; `--apply` to create them. |
| `review-unpushed.sh`, `vreview-unpushed.sh` | Step through unpushed commits (`vreview-` in a viewer). Moved here from the assembler directory. |
| `tests/test_layout.py` | Guards the directory layout: `asm/`, `editor/` and `prog8/` at the top, asm1 in the attic, no live file naming an old path. |
| `makerom.py` | The 2020 Ben Eater-style ROM image generator (`rom.bin`). |

Each of `upload/`, `lcd-ocr/` and `tests/` also has its own README: [`upload/`](upload/README.md), [`lcd-ocr/`](lcd-ocr/README.md), [`tests/`](tests/README.md).

Older per-baud-rate copies of the upload scripts are in `attic/`.
