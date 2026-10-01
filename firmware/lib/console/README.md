# console

Text consoles for the character LCD, and a command prompt.

- `console.inc`, `full_screen_console.inc`, `full_screen_console_flexible.inc`, `full_screen_console_flexible_line_based.inc`: successively more general LCD consoles (`console_initialize`, `console_print_character`, ...). The flexible ones take `CONSOLE_WIDTH` and `CONSOLE_HEIGHT`; the line-based one edits a line with a cursor.
- `command_table.inc`: looks a typed name up in a table (`CT_COMMANDS`: zero-terminated name, then handler address).
- `console_repl.inc`: a read-eval loop (`cr_repl`) joining `graphics_console.inc` and the command table.
