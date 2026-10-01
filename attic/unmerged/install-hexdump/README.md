# install-hexdump (5 patches, 2026-03-28)

Branch `claude/install-hexdump-5CahY` (tag `archive/claude/install-hexdump-5CahY`), exported with `git format-patch`; it applies to `assembler2/` as of 2026-03-28.

- 0001-0002: a Python hello-world web app and its screenshot (now `../../assembler2/webapp/`).
- 0003: a 6502 assembly web server plus an emulator TCP socket API (`socket_bind`, `socket_send`, ...) in the old single-file `assembler2/emulator.c`; the web server is now `../../assembler2/webserver/`.
- 0004-0005: pass the port via X/Y registers in `socket_bind`, and handle a broken pipe in `socket_send` with the carry flag.

Why it is parked: only the demo files reached the tree. The emulator socket code (patches 3-5) was never ported to the modular `emulator/`, so the web server demo cannot run.

Successor: none.
