#!/usr/bin/env python3
"""Draws schematic.svg for the FPGA SPI display interface (WIRING.md has the same connections as tables).

Run: python3 schematic.py > schematic.svg
"""
from xml.sax.saxutils import escape

ROW = 24                     # vertical pitch of signal rows
DATA = [(f"PB{i}", 10 + i, f"B{i + 1}", 18 - i, f"A{i + 1}", 2 + i, 1 + i, f"d[{i}]") for i in range(8)]
CTRL = [("PA0 E", 2, "B1", 18, "A1", 2, 9, "e"),
        ("PA1 CSB", 3, "B2", 17, "A2", 3, 10, "csb"),
        ("PA2 RSTB", 4, "B3", 16, "A3", 4, 11, "rstb"),
        ("PA5 DC", 7, "B4", 15, "A4", 5, 12, "dc"),
        (None, None, "B5", 14, "A5", 6, 13, "bl")]
LCD = [("CS", 26), ("RESET", 27), ("DC", 28), ("SDI (MOSI)", 29), ("SCK", 30), ("LED", 31), ("SDO (MISO)", 32),
       ("T_CLK", 33), ("T_CS", 34), ("T_DIN", 35), ("T_DO", 36), ("T_IRQ", 37)]

X_VIA, X_BUF, X_CMOD, X_LCD = 40, 330, 640, 1010     # left edges of the four blocks
W_VIA, W_BUF, W_CMOD, W_LCD = 130, 120, 170, 140
Y0 = 90
out = []


def text(x, y, s, anchor="start", size=12, weight="normal", fill="#1f2328"):
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
               f'fill="{fill}">{escape(s)}</text>')


def line(x1, y1, x2, y2, color="#1f2328", width=1.4, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{d}/>')


def box(x, y, w, h, title, subtitle=None):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#f6f8fa" stroke="#1f2328" '
               f'stroke-width="1.6"/>')
    text(x + w / 2, y - 22, title, "middle", 14, "bold")
    if subtitle:
        text(x + w / 2, y - 7, subtitle, "middle", 11, fill="#59636e")


def resistor(x, y, label):
    """A 10k tie drawn horizontally from (x, y) to a rail label at its right."""
    line(x, y, x + 12, y)
    out.append(f'<rect x="{x + 12}" y="{y - 5}" width="26" height="10" fill="#ffffff" stroke="#1f2328"/>')
    line(x + 38, y, x + 50, y)
    text(x + 54, y + 4, label, size=11, fill="#59636e")


def buffer_block(rows, y_top, name, note):
    h = len(rows) * ROW + 16
    box(X_BUF, y_top - 18, W_BUF, h + 4, name, note)
    for i, (sig, via_pin, b, b_pin, a, a_pin, cmod_pin, fpga) in enumerate(rows):
        y = y_top + i * ROW
        text(X_BUF + 8, y + 4, f"{b_pin} {b}", size=11)
        text(X_BUF + W_BUF - 8, y + 4, f"{a} {a_pin}", "end", 11)
        # A side to the Cmod
        line(X_BUF + W_BUF, y, X_CMOD, y)
        text(X_CMOD + 8, y + 4, f"{cmod_pin}", size=11, weight="bold")
        text(X_CMOD + 32, y + 4, fpga, size=11, fill="#59636e")
        if sig:   # B side from Michael
            line(X_VIA + W_VIA, y, X_BUF, y)
            text(X_VIA + W_VIA - 8, y + 4, f"{sig} {via_pin}", "end", 11)
        else:     # backlight level: a tie for now
            out.append(f'<line x1="{X_BUF}" y1="{y}" x2="{X_BUF - 70}" y2="{y}" stroke="#1f2328" stroke-width="1.4"/>')
            out.append(f'<rect x="{X_BUF - 110}" y="{y - 5}" width="26" height="10" fill="#ffffff" stroke="#1f2328"/>')
            line(X_BUF - 84, y, X_BUF - 70, y)
            line(X_BUF - 124, y, X_BUF - 110, y)
            text(X_BUF - 128, y + 4, "3.3 V, 10k (backlight on)", "end", 11, fill="#59636e")
    return y_top + len(rows) * ROW


y_data, y_ctrl = Y0, Y0 + 8 * ROW + 70
end_ctrl = y_ctrl + len(CTRL) * ROW

# Cmod A7 (drawn first so the buffers' pin labels land on top of it)
cmod_top, cmod_bottom = Y0 - 18, end_ctrl + 130
box(X_CMOD, cmod_top, W_CMOD, cmod_bottom - cmod_top, "Cmod A7-35T", "FPGA, 3.3 V I/O")
text(X_CMOD + W_CMOD / 2, cmod_bottom - 64, "12 MHz clock", "middle", 11, fill="#59636e")
text(X_CMOD + W_CMOD / 2, cmod_bottom - 48, "LD1 traffic, LD2 selected", "middle", 11, fill="#59636e")
text(X_CMOD + 8, cmod_bottom - 22, "24 VU", size=11, weight="bold")
text(X_CMOD + W_CMOD - 8, cmod_bottom - 22, "GND 25", "end", 11, weight="bold")

# Michael's VIA: its box stops above the backlight row, which has no VIA signal
box(X_VIA, Y0 - 18, W_VIA, (y_ctrl + 3 * ROW + 14) - (Y0 - 18), "Michael", "W65C22 VIA (5 V)")
buffer_block(DATA, y_data, "U1 74LVC245", "data; DIR, /OE = GND (B→A)")
buffer_block(CTRL, y_ctrl, "U2 74LVC245", "control; DIR, /OE = GND (B→A)")
for i, (b, b_pin) in enumerate([("B6", 13), ("B7", 12), ("B8", 11)]):
    y = end_ctrl + 30 + i * 18
    text(X_BUF - 6, y + 4, f"{b_pin} {b}", "end", 11)
    resistor(X_BUF - 2, y, "")
text(X_BUF + 52, end_ctrl + 66, "10k ties (unused inputs)", size=11, fill="#59636e")

# Display
lcd_y0 = Y0 + 2 * ROW
box(X_LCD, lcd_y0 - 2 * ROW - 18, W_LCD, (len(LCD) + 2) * ROW + 16, "ILI9341 module", "240×320, J1 open")
text(X_LCD + 8, lcd_y0 - 2 * ROW + 4, "VCC", size=11)
text(X_LCD + 8, lcd_y0 - ROW + 4, "GND", size=11)
line(X_LCD, lcd_y0 - 2 * ROW, X_LCD - 40, lcd_y0 - 2 * ROW)
text(X_LCD - 44, lcd_y0 - 2 * ROW + 4, "5 V", "end", 11, fill="#59636e")
line(X_LCD, lcd_y0 - ROW, X_LCD - 40, lcd_y0 - ROW)
text(X_LCD - 44, lcd_y0 - ROW + 4, "GND (Cmod 25)", "end", 11, fill="#59636e")
for i, (name, pin) in enumerate(LCD):
    y = lcd_y0 + i * ROW
    dashed = name in ("SDO (MISO)", "T_DO", "T_IRQ")
    line(X_CMOD + W_CMOD, y, X_LCD, y, dash="5 4" if dashed else None)
    text(X_CMOD + W_CMOD - 8, y + 4, f"{pin}", "end", 11, weight="bold")
    text(X_LCD + 8, y + 4, name, size=11)
text(X_CMOD + W_CMOD + 6, lcd_y0 + len(LCD) * ROW + 4, "dashed: wired, not yet used", size=11, fill="#59636e")

# Power
py = cmod_bottom + 50
text(X_VIA, py, "Power", size=14, weight="bold")
items = ["Michael 5 V → 5 V rail → 3.3 V regulator → 3.3 V rail → U1, U2 VCC (pin 20), 100 nF each",
         "5 V rail → diode (band towards the Cmod) → Cmod VU (24); USB only needed for programming",
         "5 V rail → display VCC; Michael GND, both GND rails, U1/U2 pin 10, Cmod 25 and display GND joined"]
for i, s in enumerate(items):
    text(X_VIA, py + 22 + i * 18, s, size=12)

height = py + 22 + len(items) * 18 + 20
width = X_LCD + W_LCD + 30
print(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
      f'font-family="Helvetica, Arial, sans-serif">')
print(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')
print("\n".join(out))
print("</svg>")
