# LCD OCR

Reads the Wendy 2 16x2 LCD through a webcam, for checking what a real board shows.

- `lcd_read`: captures, rectifies and decodes (`lcd_ocr.py --capture`); writes `/tmp/lcd-ocr/`. `lcd_read --calibrate` saves the LCD corners.
- `calibrate.py`: the calibration (corners, then the per-cell glyph font), saved to `lcd_calibration.json`.
- `lcd_ocr.py`: the capture and decode pipeline. `lcd_inspect.py`: a side-by-side diagnostic of the last capture.
- `apply_font_to_emulator.py`: copies the captured font into the emulator's HD44780 ROM tables.

Setup: upload `firmware/programs/wendy2/lcd_calibrate.s` (lights all cells), then run `lcd_read --calibrate`. It uses the local, untracked `snap.sh` and `lcd_calibration.json` at the repository root. Needs OpenCV and numpy.
