"""The text mode's model (text_screen.py) against the code it mirrors: the ROM's LCD screen,
firmware/lib/lcd/lcd_screen.inc. Random sequences of the same calls run through lcd_screen.inc on the
emulator's Michael (4 rows of 20), which shows the result on its LCD, and through the model; the screens
must match. Rows and columns are 1-based for lcd_screen.inc, 0-based for the model.
"""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', '..', 'tools', 'tests'))
import michael_emulator  # noqa: E402
from text_screen import TextScreen  # noqa: E402

ROWS, COLS = 4, 20
PROGRAM = """
  .include base_config_v2.inc
LCD_SCREEN       = $0300
LCD_SCREEN_STATE = LCD_SCREEN + 80
  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine
  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include ASCII.inc
  .include lcd_screen.inc
program_start:
  ldx #$ff
  txs
  jsr reset_and_enable_display_no_cursor
  jsr lcd_screen_initialize
{calls}
  jsr lcd_screen_flush
  stp
"""

# The calls: (name, lcd_screen.inc's routine, how many arguments)
CALLS = [('put', 'lcd_screen_write', 1), ('goto', 'lcd_screen_goto', 2), ('clear', 'lcd_screen_clear', 0),
         ('clear_eol', 'lcd_screen_clear_eol', 0), ('insert', 'lcd_screen_insert', 1),
         ('delete', 'lcd_screen_delete', 1), ('region', 'lcd_screen_region', 2),
         ('region_reset', 'lcd_screen_region_reset', 0), ('scroll_up', 'lcd_screen_scroll_up', 1),
         ('scroll_down', 'lcd_screen_scroll_down', 1), ('insert_lines', 'lcd_screen_insert_lines', 1),
         ('delete_lines', 'lcd_screen_delete_lines', 1)]


def random_calls(rng, n):
    calls = []
    for _ in range(n):
        name, routine, args = rng.choice(CALLS[3:] * 2 + [CALLS[1]] * 6 + [CALLS[0]] * 40)   # mostly writing
        if rng.random() < 0.005:
            name, routine, args = CALLS[2]                              # clear, rarely
        if name == 'put':
            control = rng.random() < 0.1
            values = [rng.choice([0x08, 0x0A, 0x0D, 0x07]) if control else ord(rng.choice('abcdefghijklmnopqrstuvwxyz0123456789'))]
        elif args == 2:
            values = [rng.randrange(ROWS + 1), rng.randrange(COLS + 2)]   # 0-based, some past the end
        else:
            values = [rng.choice([0, 1, 1, 1, 2, 3, 9])][:args]
        calls.append((name, routine, values))
    return calls


def assemble(calls):
    lines = []
    for name, routine, values in calls:
        if name == 'put':
            lines.append(f'  lda #${values[0]:02x}')
        elif name in ('goto', 'region'):
            lines += [f'  lda #{values[0] + 1}', f'  ldy #{values[1] + 1}']
        elif values:
            lines.append(f'  lda #{values[0]}')
        lines.append(f'  jsr {routine}')
    return PROGRAM.replace('{calls}', '\n'.join(lines))


def lcd_rows(report):
    lines = report.split('\n')
    start = lines.index('michael: lcd:') + 1
    return [line.strip()[1:-1] for line in lines[start:start + ROWS]]


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class ModelAgainstLcdScreenTest(unittest.TestCase):
    def test_random_sequences(self):
        michael_emulator.build_emulator()
        for seed in range(200):
            with self.subTest(seed=seed):
                calls = random_calls(random.Random(seed), 50)
                model = TextScreen(ROWS, COLS)
                model.text_on()
                for name, _, values in calls:
                    getattr(model, name)(*values)
                _, report = michael_emulator.run(source=assemble(calls), cycle_cap=20_000_000)
                self.assertEqual(lcd_rows(report), [model.text(r) for r in range(ROWS)], report)


if __name__ == '__main__':
    unittest.main()
