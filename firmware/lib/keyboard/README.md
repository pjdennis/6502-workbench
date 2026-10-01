# keyboard

PS/2 keyboard support, used by Michael's programs and ROM (keyboard board with shift registers).

- `keyboard_driver.inc`: the interrupt-driven driver: `keyboard_initialize`, `keyboard_get_char`, `keyboard_send_command`, `keyboard_set_leds`, modifier and lock-key tracking. It needs `KB_BUFFER_*` routines (see `core/simple_buffer.inc`), `copy_memory` and its `CP_M_*` locations (`core/copy_memory.inc`), `INTERRUPT_ROUTINE` and `KB_ZERO_PAGE_BASE`. Optional `callback_key_*` hooks get arrows, Escape and F1.
- `key_codes.inc`: the key codes, ASCII-based and extended to every PS/2 key. `key_names.inc` is generated from it (the command is in `COMMANDS`). `key_translation_tables.inc`: PS/2 set 2 to key code tables.
- `keyboard_typematic.inc`: repeat rate and delay constants. `show_keys_on_screen.inc`: a key-code viewer.
- `keyboard_keys.inc`: keys in the form the editor's terminal interface wants (used by the Michael ROM services).
