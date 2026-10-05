# Michael FPGA: text mode

Stage 3 of the [FPGA bus plan](../../../../docs/michael-fpga-bus-plan.md): the FPGA keeps a 20 by 20 grid of
characters and draws it on the display itself, so Michael sends a character code where it used to send about
400 bytes of pixels. Text mode is the bus's first long-form device (`$80`, then an operation); its operations
and their rules are in the plan's
[text mode section](../../../../docs/michael-fpga-bus-plan.md#text-mode-device-80): the screen behaves as the
ROM's screen on the LCD does ([`lcd_screen.inc`](../../../../firmware/lib/lcd/lcd_screen.inc)), so the editor
sees the same screen on either display.

## The pieces

- [`../rtl/text_grid.v`](../rtl/text_grid.v): the grid. Operations queue and run in turn; one engine does
  every shift (insert, delete, the scrolls, lines). A cell is marked dirty when a write changes it, so
  rewriting the same text, or moving blank rows onto blank rows, draws nothing; so are the cells a shown
  cursor leaves or reaches.
- [`../rtl/text_render.v`](../rtl/text_render.v): draws the dirty cells, each as Michael's driver draws a
  character, with reverse video and the blinking cursor (the bottom two pixel rows of its cell), through
  [`../rtl/display_spi.v`](../rtl/display_spi.v)'s second input.
- **Hardware scrolling.** Scrolling the whole region (and inserting or deleting lines at its top row)
  doesn't redraw it: the grid moves the cells with their dirty marks and changes an offset, and the
  renderer has the display's own scroll (VSCRDEF, VSCRSADD) move the region's picture, drawing only the rows
  that come in blank. So that nothing stale shows while it moves, the grid first asks the renderer, which
  draws what's dirty, takes the cursor off the glass and blanks the rows that leave (their memory is where the
  new rows show); after the scroll it draws nothing for a frame, as the display takes it up at its next. Each row is drawn in the memory row the scroll shows where it belongs. The frame
  memory runs from the bottom row up, so the top fixed area is the rows below the region:
  [`ili9341.py`](ili9341.py) models it, and [`test_ili9341.py`](test_ili9341.py) checks the model against
  Michael's graphic driver's whole-screen scroll, which works on the board.
- The font is [`firmware/lib/graphics/font_12x16.txt`](../../../../firmware/lib/graphics/font_12x16.txt), shared
  with Michael's graphics driver: [`tools/font_12x16.py`](../../../../tools/font_12x16.py) generates the
  firmware's table, the emulator's ([`emulator/chips/font_12x16.h`](../../../../emulator/chips/font_12x16.h)),
  and, for the FPGA builds (`../text.mk`), `build/font_12x16.vh`.
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
  the model holds, on the glass and in memory. A region's scroll must redraw only its new rows, only cells
  that change may be drawn, and the glass, scanned frame by frame as the panel does, must never show a cell
  anything it doesn't hold before, between or after the operations of a scroll. Most tests use
  a 6 by 8 grid: a full screen takes about 18 s to simulate.

## On the board

[`board_check.py`](board_check.py) checks text mode without anyone watching the display: it draws `debug.py
text`'s screen through the debug port, loads the display-probe design (which leaves the display as it is),
reads cells back out of the display's memory and compares them with the model, then reloads the bus design and
redraws. On 2026-10-04: PASS, 112 cells, before and with hardware scrolling (the demo scrolls a region,
so its rows are in rotated memory rows, where the check expects them). What it can't see is the glass: that
the region shows scrolled the right way between its fixed areas is for a person to check, with `debug.py
text` (rows 6-17 show "row 7" to "row 18", row 18 is blank, and rows 0-5 and 19 are as drawn).
