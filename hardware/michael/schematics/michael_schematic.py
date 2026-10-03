#!/usr/bin/env python3
"""Michael as built (2026-10-03), in three sheets drawn with net labels: michael-core.svg (CPU, memory,
clock, reset), michael-io.svg (the VIA and what hangs off it) and michael-fpga-display.svg (the FPGA display
interface; ../fpga/spi-display/WIRING.md has its connections as tables).

Run: python3 michael_schematic.py   (writes the SVGs beside this file)
tools/tests/test_michael_schematic.py checks the netlist against the firmware and the FPGA design.
"""
import os

from schematic_svg import Board, Sheet, MUTED, NOTE

SUBTITLE = "Michael as built, 2026-10-03. Pins with the same label are connected; × is not connected."

W65C02 = (["VPB", "RDY", "PHI1O", "IRQB", "MLB", "NMIB", "SYNC", "VDD"] + [f"A{i}" for i in range(12)] +
          ["VSS", "A12", "A13", "A14", "A15"] + [f"D{i}" for i in range(7, -1, -1)] +
          ["RWB", "NC", "BE", "PHI2", "SOB", "PHI2O", "RESB"])
W65C22 = (["VSS"] + [f"PA{i}" for i in range(8)] + [f"PB{i}" for i in range(8)] +
          ["CB1", "CB2", "VDD", "IRQB", "RWB", "CS2B", "CS1", "PHI2"] + [f"D{i}" for i in range(7, -1, -1)] +
          ["RESB", "RS3", "RS2", "RS1", "RS0", "CA2", "CA1"])
X28C256 = ["A14", "A12", "A7", "A6", "A5", "A4", "A3", "A2", "A1", "A0", "D0", "D1", "D2", "GND", "D3", "D4",
           "D5", "D6", "D7", "/CE", "A10", "/OE", "A11", "A9", "A8", "A13", "/WE", "VCC"]
LVC245 = ["DIR"] + [f"A{i}" for i in range(1, 9)] + ["GND"] + [f"B{i}" for i in range(8, 0, -1)] + ["/OE", "VCC"]
CMOD = [f"PIO{i}" for i in range(1, 49)]
CMOD[23], CMOD[24] = "VU", "GND"

BUSES = {f"A{i}": f"A{i}" for i in range(16)} | {f"D{i}": f"D{i}" for i in range(8)}
PORT_A_USES = {"PA0": "FPGA E", "PA1": "FPGA CSB", "PA2": "LED, FPGA RSTB", "PA3": "keyboard SOLB",
               "PA4": "keyboard SOEB", "PA5": "LCD RS, kbd START/ACK, FPGA DC", "PA6": "LCD RW, kbd PARITY",
               "PA7": "LCD E"}


def core(board):
    s = Sheet(board, "Michael: CPU, memory, clock and reset (1 of 3)", SUBTITLE, 1160, 1060)
    s.dip("U1", "W65C02S", 170, 110, W65C02, BUSES | {
        "RDY": "RDY", "IRQB": "IRQB", "NMIB": "+5V", "VDD": "+5V", "VSS": "GND", "RWB": "RWB", "BE": "+5V",
        "PHI2": "PHI2", "RESB": "RESB"}, width=130)
    memory = {name: name for name in X28C256 if name[0] in "AD"} | {"GND": "GND", "VCC": "+5V"}
    s.dip("U2", "AT28C256 EEPROM", 570, 110, X28C256, memory | {"/CE": "/A15", "/OE": "GND", "/WE": "+5V"})
    s.dip("U6", "62256 RAM", 900, 110, X28C256, memory | {"/CE": "RAM/CE", "/OE": "A14", "/WE": "RWB"})

    y = 600
    s.ic("X1", "2 MHz oscillator", 170, y, left=[(1, "NC", None), (7, "GND", "GND")],
         right=[(14, "VCC", "+5V"), (8, "OUT", "PHI2")], width=80)
    s.two_pin("resistor", "R1", "1k", 420, y, "+5V", "RESB")
    s.two_pin("capacitor", "C1", "0.1 µF", 500, y, "RESB", "GND")
    s.two_pin("switch", "SW1", "reset", 590, y, "RESB", "GND")
    s.two_pin("resistor", "R2", "1k", 670, y, "+5V", "RDY")
    u4 = [(1, "1A", None), (2, "1B", None), (3, "1Y", None), (7, "GND", "GND"), (14, "VCC", "+5V")]
    for i, (unit, a, b, out) in enumerate((("U4D", (12, "A15"), (13, "A15"), (11, "/A15")),
                                           ("U4C", (9, "PHI2"), (10, "/A15"), (8, "RAM/CE")),
                                           ("U4B", (4, "A14"), (5, "/A15"), (6, "VIA/CS2")))):
        gy = y + 10 + i * 70
        u4 += s.nand(830, gy, a, b, out)
        s.text(852, gy - 6, unit, "middle", 11.5, "bold")
    s.text(852, y + 228, "74HC00; U4A (1–3) unused", "middle", 10.5, fill=MUTED)
    board.add("U4", u4)
    for i in range(3):
        s.two_pin("capacitor", f"C{i + 2}", "0.1 µF", 420 + i * 85, y + 150, "+5V", "GND", length=70)
    s.text(505, y + 255, "bypass", "middle", 10.5, fill=MUTED)

    y = s.note(24, 880, [
        "As Ben Eater's schematic (ben-eater-6502-schematic.png), with the same reference designators (new parts start at R8),",
        "except that X1 runs at 2 MHz (CLOCK_FREQ_KHZ = 2000 in base_config_v2.inc; Ben's is 1 MHz).",
        "Memory map: RAM $0000–$3FFF, VIA $6000–$7FFF, ROM $8000–$FFFF. Writes to $4000–$7FFF also go to the RAM, into its",
        "upper half, which can't be read (A14 drives /OE).",
        "RESB also goes to the VIA and, through Z1, to the USB serial adapter's DTR (sheet 2)."], "Notes")
    s.note(24, y + 6, [
        "X1: the part, and that it is 2 MHz (the firmware's timing says so).",
        "U4A: Ben's schematic doesn't show its inputs. Tied to GND or +5V, or left open?",
        "Where Michael's +5V comes from (the USB serial adapter, or a separate supply)."], "To confirm", NOTE)
    return s


def io(board):
    s = Sheet(board, "Michael: VIA, LCD, LED, keyboard board and serial (2 of 3)", SUBTITLE, 1300, 1000)
    via = {f"P{p}{i}": f"P{p}{i}" for p in "AB" for i in range(8)} | {
        f"RS{i}": f"A{i}" for i in range(4)} | {f"D{i}": f"D{i}" for i in range(8)} | {
        "VSS": "GND", "VDD": "+5V", "IRQB": "IRQB", "RWB": "RWB", "CS2B": "VIA/CS2", "CS1": "A13",
        "PHI2": "PHI2", "RESB": "RESB", "CA2": "CA2", "CB2": "CB2"}
    s.dip("U5", "W65C22 VIA", 390, 110, W65C22, via, width=130, notes=PORT_A_USES | {
        "CA2": "keyboard IRQ", "CB2": "serial in", "CB1": "shift clock out"})

    lcd = [(1, "VSS", "GND"), (2, "VDD", "+5V"), (3, "V0", "V0"), (4, "RS", "PA5"), (5, "RW", "PA6"),
           (6, "E", "PA7")] + [(7 + i, f"DB{i}", f"PB{i}") for i in range(8)] + [(15, "A", "+5V"),
                                                                                 (16, "K", "GND")]
    s.ic("U3", "20×4 LCD (HD44780)", 790, 110, left=lcd, width=110)
    s.pot("RV1", "10k contrast", 860, 490, "+5V", "V0", "GND")

    s.two_pin("resistor", "R8", "?", 790, 650, "PA2", "LED")
    s.two_pin("led", "D1", "LED", 870, 650, "LED", "GND", names=("A", "K"))

    kbd = [(1, "VCC", "+5V"), (2, "GND", "GND"), (3, "IRQ", "CA2"), (4, "KBD_CLK_OUT", "PA3"),
           (5, "REG_OE", "PA4"), (6, "DE", "PA5"), (7, "DP", "PA6")] + [
        (8 + i, f"D{7 - i}", f"PB{7 - i}") for i in range(8)]
    s.ic("J1", "keyboard board (its J2)", 1120, 110, left=kbd, width=120,
         caption="michael-bidirectional-PS2-…-v-1.0.pdf")
    serial = [(None, "DTR", "DTR"), (None, "RXD", None), (None, "TXD", "CB2"), (None, "5V", None),
              (None, "GND", "GND")]
    s.ic("J2", "USB serial (CP2102)", 1120, 500, left=serial, width=120, caption="to the host PC")
    s.two_pin("box", "Z1", "DTR → reset", 1000, 640, "DTR", "RESB")

    y = s.note(24, 800, [
        "PORTB is shared by the LCD, the keyboard board (its 74HC595s drive it while SOEB is low; its 74HC165s load it",
        "while SOLB is low) and the FPGA. The keyboard driver saves and restores PORTA, PORTB and their DDRs in its interrupt.",
        "Serial is received only: CB2 is the shift register's input, timed by T2 (firmware/lib/serial/), so CB1 is its clock out.",
        "J1's pins and the PA3–PA6 uses are from base_config_v2.inc, keyboard_driver.inc and the keyboard board's schematic."],
        "Notes")
    s.note(24, y + 6, [
        "Ben's buttons SW2–SW6 and pull-ups R3–R7 on PA0–PA4: removed (those pins now go to the FPGA, LED and keyboard)?",
        "Z1: how DTR reaches RESB (wire, diode or capacitor). Uploads hold DTR for 0.1 s to reset and then release it.",
        "LED polarity and R8: upload_v3.inc lights the LED by setting PA2 (as drawn); michael_ports.inc's comment says the opposite.",
        "LCD backlight (pins 15 and 16) straight to +5V and GND, as Ben's? J2's 5V: connected?"], "To confirm", NOTE)
    return s


def fpga(board):
    s = Sheet(board, "Michael: FPGA display interface (3 of 3)", SUBTITLE + " U7, U8 and U10 run from +3V3.",
              1360, 1060)
    data = {f"B{i + 1}": f"PB{i}" for i in range(8)} | {f"A{i + 1}": f"d[{i}]" for i in range(8)}
    power = {"DIR": "GND", "/OE": "GND", "GND": "GND", "VCC": "+3V3"}
    s.dip("U7", "74LVC245 (data)", 330, 110, LVC245, data | power, width=110)
    control = {"B1": "PA0", "B2": "PA1", "B3": "PA2", "B4": "PA5", "B5": "U8.B5", "B6": "U8.B6", "B7": "U8.B7",
               "B8": "U8.B8", "A1": "e", "A2": "csb", "A3": "rstb", "A4": "dc", "A5": "bl"}
    s.dip("U8", "74LVC245 (control)", 330, 420, LVC245, control | power, width=110)
    s.two_pin("capacitor", "C5", "100 nF", 110, 360, "+3V3", "GND", length=70)
    s.two_pin("capacitor", "C6", "100 nF", 180, 360, "+3V3", "GND", length=70)
    s.two_pin("resistor", "R9", "10k", 110, 700, "+3V3", "U8.B5")
    s.text(110, 830, "backlight on", "middle", 10.5, fill=MUTED)
    for i in range(3):
        s.two_pin("resistor", f"R{10 + i}", "10k", 180 + i * 70, 700, f"U8.B{6 + i}", "TIE")

    lcd = ["lcd_cs", "lcd_reset", "lcd_dc", "lcd_mosi", "lcd_sck", "lcd_led", "lcd_miso"]
    cmod = {i + 1: f"d[{i}]" for i in range(8)} | {9: "e", 10: "csb", 11: "rstb", 12: "dc", 13: "bl",
                                                   24: "VU", 25: "GND"} | {26 + i: n for i, n in enumerate(lcd)}
    s.dip("U9", "Cmod A7-35T", 720, 110, CMOD, cmod, width=110,
          caption="33–37 reserved for the touch controller")

    display = [(None, "VCC", "+3V3"), (None, "GND", "GND"), (None, "CS", "lcd_cs"), (None, "RESET", "lcd_reset"),
               (None, "DC", "lcd_dc"), (None, "SDI (MOSI)", "lcd_mosi"), (None, "SCK", "lcd_sck"),
               (None, "LED", "lcd_led"), (None, "SDO (MISO)", "lcd_miso")] + [
        (None, n, None) for n in ("T_CLK", "T_CS", "T_DIN", "T_DO", "T_IRQ")]
    s.ic("U10", "ILI9341 240×320 (Adafruit)", 1130, 300, left=display, width=150)

    s.ic("U11", "3.3 V regulator", 1130, 680, left=[(None, "IN", "+5V"), (None, "GND", "GND")],
         right=[(None, "OUT", "+3V3")], width=110)
    s.two_pin("diode", "D2", "diode", 1060, 820, "+5V", "VU", names=("A", "K"))

    y = s.note(24, 900, [
        "From ../fpga/spi-display/WIRING.md. Both '245s pass Michael's 5 V signals (B) to the Cmod (A) at 3.3 V: DIR and /OE are grounded.",
        "Cmod pins carry the FPGA design's port names (spi-display/constr/cmod_a7.xdc). U10's SDO is read only by the display probe.",
        "The Cmod runs from Michael's +5V through D2 (band towards the Cmod), so its USB is needed only for programming."], "Notes")
    s.note(24, y + 6, [
        "R10–R12 (the unused inputs' ties): which rail TIE is, +3V3 or GND. U11 and D2: the parts, and U11's capacitors."],
        "To confirm", NOTE)
    return s


def build():
    board = Board()
    return board, {"michael-core.svg": core(board), "michael-io.svg": io(board),
                   "michael-fpga-display.svg": fpga(board)}


def board():
    return build()[0]


def sheets():
    return {name: sheet.svg() for name, sheet in build()[1].items()}


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for name, svg in sheets().items():
        with open(os.path.join(here, name), "w") as f:
            f.write(svg)
