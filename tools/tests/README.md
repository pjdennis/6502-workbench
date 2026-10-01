# Tool tests

Python `unittest` modules for the host tools and cross-cutting repository checks. Run from the repository root:

```bash
python3 -m unittest discover -s tools/tests -v
```

`tools/check_all.sh firmware` runs them. Tests that need `vasm6502_oldstyle` or the emulator skip when it is missing.

| Test | Checks |
|---|---|
| `test_layout.py`, `test_doc_links.py` | the directory layout, and that relative links resolve in the root README and CLAUDE.md, `docs/`, the area CLAUDE.md files and every README outside `attic/` |
| `test_firmware_manifest.py`, `test_vasm_portability.py` | the manifest tool, and the firmware rules that keep binaries vasm-version independent |
| `test_upload_frame.py`, `test_transfer.py`, `test_serial_daemon.py`, `test_upload_scripts.py` | the upload formats, sender, daemon and `compile_and_upload_*.sh` |
| `test_michael_rom.py`, `test_michael_keyboard.py`, `test_michael_start_labels.py` | the Michael ROM, the keyboard programs and `michael_ram_map.s` on the emulator, and that uploaded programs have `start` labels |
| `test_create_tags.py` | `tools/reorg/create_tags.sh` |

The 6502 programs the Michael ROM tests upload are in [`michael/`](michael/README.md).
