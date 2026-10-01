# sound

Square-wave notes from the VIA's timer 1 (`start_note` loads its latches), and morse.

- `sound.inc`: `start_note` (A = note index), `stop_note`.
- `musical_notes.inc`: half-period of each note in CPU cycles, computed from `CLOCK_FREQ_KHZ`. `musical_notes_tables.inc`: the note lookup table.
- `morse.inc`: `initialize_morse`, `send_morse_string` and related routines, on `MORSE_PORT` (default `PORTA`), with a 200 ms unit.

Songs that use these are in `../tasks/`.
