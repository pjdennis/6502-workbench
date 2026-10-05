# Michael FPGA: text mode

Stage 3 of the [FPGA bus plan](../../../../docs/michael-fpga-bus-plan.md): the FPGA keeps a 20 by 20 grid of
characters and draws it on the display itself, so Michael sends a character code where it used to send about
400 bytes of pixels. The text commands (`$20`–`$30`) and their rules are in the plan's
[text mode section](../../../../docs/michael-fpga-bus-plan.md#text-mode-2x-and-3x): the screen behaves as the
ROM's screen on the LCD does ([`lcd_screen.inc`](../../../../firmware/lib/lcd/lcd_screen.inc)), so the editor
sees the same screen on either display.

## The pieces

- [`../rtl/text_grid.v`](../rtl/text_grid.v): the grid. Operations queue and run in turn; one engine does
  every shift (insert, delete, the scrolls, lines). Every cell written, and every cell the cursor leaves or
  reaches, is marked dirty.
- [`../rtl/text_render.v`](../rtl/text_render.v): draws the dirty cells, each as Michael's driver draws a
  character, with reverse video and the blinking cursor (the bottom two pixel rows of its cell), through
  [`../rtl/display_spi.v`](../rtl/display_spi.v)'s second input.
- The font is [`firmware/lib/graphics/font_12x16.txt`](../../../../firmware/lib/graphics/font_12x16.txt), shared
  with Michael's graphics driver: [`tools/font_12x16.py`](../../../../tools/font_12x16.py) generates the
  firmware's table and, for the FPGA builds (`../text.mk`), `build/font_12x16.vh`.
- The bus design ([`../bus/`](../bus/)) puts them behind [`../rtl/bus_control.v`](../rtl/bus_control.v), and
  [`../bus/debug.py`](../bus/debug.py) has the text commands, and `debug.py text`, a screen of them.

## Tests

`make test` in `hardware/michael/fpga` runs these (with Icarus Verilog):

- [`text_screen.py`](text_screen.py): the model, with [`test_text_screen.py`](test_text_screen.py) pinning each
  rule, and [`test_text_screen_vs_lcd.py`](test_text_screen_vs_lcd.py) running random call sequences through
  `lcd_screen.inc` on the emulator's Michael and the model, comparing the screens.
- [`test_text_grid.py`](test_text_grid.py): the grid's RTL against the model, directed and random.
- [`test_text_render.py`](test_text_render.py): the grid, the renderer and the display queue together; a model
  panel ([`ili9341.py`](ili9341.py)) turns the display's SPI bytes into pixels, and every cell must show what
  the model holds. Most tests use a 6 by 8 grid: a full screen takes about 18 s to simulate.

## On the board

[`board_check.py`](board_check.py) checks text mode without anyone watching the display: it draws `debug.py
text`'s screen through the debug port, loads the display-probe design (which leaves the display as it is),
reads cells back out of the display's memory and compares them with the model, then reloads the bus design and
redraws. On 2026-10-04: PASS, 112 cells.
