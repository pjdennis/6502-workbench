# editor/bin

Launchers for the editor. The console and terminal ones take the file to edit and any further emulator options; `editor-michael.sh` takes only emulator options, and `editor-michael-upload.sh` takes `transfer.py` options. Build first with `tools/build_all.sh` (the emulator, the assembler and the editor; the editor's tests write the `*_stable.out` builds the scripts run).

| Script | Runs |
|---|---|
| `editor.sh` | terminal build (`editor_terminal_stable.out`) at 19200 baud, 2 MHz: the default |
| `editor-terminal-300.sh`, `editor-terminal-9600.sh`, `editor-terminal-19200.sh` | terminal build at that baud rate, 2 MHz |
| `editor-terminal-9600-repaint.sh` | as the 9600 one, with the emulator's `--show-repaints` |
| `editor-fast.sh` | console build (`editor_stable.out`) at 2 MHz, no serial link |
| `editor-slow-console.sh` | console build at 0.5 MHz |
| `editor-michael.sh` | the `direct_io` + `michael` build on the emulated Michael board (ROM, serial loader, 20x4 LCD drawn in the terminal); Ctrl-] quits; with `--web` the board is in the browser instead (`http://127.0.0.1:8080/`, Ctrl-C quits); needs `vasm6502_oldstyle` |
| `editor-michael-upload.sh` | builds the Michael image (`../michael_image.py`) and uploads it to a real board; options go to `tools/upload/transfer.py` |

Run them from anywhere; they find the repository root themselves.
