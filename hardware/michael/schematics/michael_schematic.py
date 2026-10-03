#!/usr/bin/env python3
"""Michael's schematics, drawn with net labels, in two sets of three sheets: michael-core.svg (CPU, memory,
clock, reset), michael-io.svg (the VIA and what hangs off it) and michael-fpga-display.svg (the FPGA display
interface; ../fpga/spi-display/WIRING.md has its connections as tables).

The top-level SVGs are Michael as built (2026-10-03). Those in planned/ are Michael once the FPGA bus plan
(docs/michael-fpga-bus-plan.md) is complete: they differ in the LED and the FPGA interface's wiring.

Run: python3 michael_schematic.py   (writes the SVGs beside this file)
tools/tests/test_michael_schematic.py checks the netlists against the firmware and the FPGA design.
"""
import os

from schematic_svg import Board, Sheet, MUTED

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
# The Adafruit 2.8" TFT breakout's header, from the photo of the board (2026-10-03)
ADAFRUIT_TFT = ["GND", "Vin", "3Vo", "CLK", "MISO", "MOSI", "CS", "D/C", "RST", "Lite", "GND", "IRQ", "SDA", "SCL",
                "IM3", "IM2", "IM1", "IM0", "CCS", "CD"]
SERIAL = ["3V3", "DTR", "RXD", "TXD", "GND", "+5V"]   # the CP2102 adapter's header, in order

BUSES = {f"A{i}": f"A{i}" for i in range(16)} | {f"D{i}": f"D{i}" for i in range(8)}
PORT_A_USES = {"PA0": "FPGA E", "PA1": "FPGA CSB", "PA2": "LED, FPGA RSTB", "PA3": "keyboard SOLB",
               "PA4": "keyboard SOEB", "PA5": "LCD RS, kbd START/ACK, FPGA DC", "PA6": "LCD RW, kbd PARITY",
               "PA7": "LCD E"}
# After stage 4's pin shuffle: E on PA2, the LED on PA1, PA0 free
PLANNED_PORT_A_USES = PORT_A_USES | {"PA0": "free", "PA1": "LED", "PA2": "FPGA E", "PA4": "keyboard SOEB, FPGA",
                                     "PA5": "LCD RS, kbd START/ACK, FPGA RS", "PA6": "LCD RW, kbd PARITY, FPGA RW"}


def subtitle(planned):
    state = ("Michael once the FPGA bus plan (docs/michael-fpga-bus-plan.md) is complete. Planned, not built."
             if planned else "Michael as built, 2026-10-03.")
    return state + " Pins with the same label are connected; × is not connected."


def core(board, planned):
    s = Sheet(board, "Michael: CPU, memory, clock and reset (1 of 3)", subtitle(planned), 1160, 1080)
    s.dip("U1", "W65C02S", 170, 110, W65C02, BUSES | {
        "RDY": "RDY", "IRQB": "IRQB", "NMIB": "+5V", "VDD": "+5V", "VSS": "GND", "RWB": "RWB", "BE": "+5V",
        "PHI2": "PHI2", "RESB": "RESB"}, width=130)
    memory = {name: name for name in X28C256 if name[0] in "AD"} | {"GND": "GND", "VCC": "+5V"}
    s.dip("U2", "AT28C256 EEPROM", 570, 110, X28C256, memory | {"/CE": "/A15", "/OE": "GND", "/WE": "+5V"})
    s.dip("U6", "62256 RAM", 900, 110, X28C256, memory | {"/CE": "RAM/CE", "/OE": "A14", "/WE": "RWB"})

    y = 600
    s.ic("X1", "2 MHz oscillator", 170, y, left=[(1, "NC", None), (7, "GND", "GND")],
         right=[(14, "VCC", "+5V"), (8, "OUT", "PHI2")], width=80)
    s.two_pin("resistor", "R1", "1 kΩ", 400, y, "+5V", "RESB")
    s.two_pin("capacitor", "C1", "0.1 µF", 470, y, "RESB", "GND")
    s.two_pin("switch", "SW1", "pushbutton", 550, y, "RESB", "GND")
    s.two_pin("diode", "D3", "1N4148", 640, y, "RESB", "DTR/K", names=("A", "K"))
    s.two_pin("resistor", "R13", "220 Ω", 730, y, "DTR", "DTR/K")
    s.two_pin("resistor", "R2", "1 kΩ", 400, y + 150, "+5V", "RDY", length=70)
    for i in range(3):
        s.two_pin("capacitor", f"C{i + 2}", "0.1 µF", 480 + i * 75, y + 150, "+5V", "GND", length=70)
    s.text(555, y + 255, "bypass", "middle", 10.5, fill=MUTED)

    u4 = [(7, "GND", "GND"), (14, "VCC", "+5V")]
    for i, (unit, a, b, out) in enumerate((("U4D", (12, "A15"), (13, "A15"), (11, "/A15")),
                                           ("U4C", (9, "PHI2"), (10, "/A15"), (8, "RAM/CE")),
                                           ("U4B", (4, "A14"), (5, "/A15"), (6, "VIA/CS2")),
                                           ("U4A", (1, "+5V"), (2, "+5V"), (3, None)))):
        gy = y + 10 + i * 64
        u4 += s.nand(900, gy, a, b, out)
        s.text(922, gy - 5, unit, "middle", 11.5, "bold")
    s.text(922, y + 282, "74HC00 (U4A spare)", "middle", 10.5, fill=MUTED)
    s.add_part("U4", "74HC00", u4)

    y = s.note(24, 910, [
        "As Ben Eater's schematic (ben-eater-6502-schematic.png), with the same reference designators (new parts start at R8),",
        "except that X1 runs at 2 MHz (a CQ 2.000 oscillator) and DTR from the USB serial adapter (sheet 2) can also reset.",
        "DTR low pulls RESB low through R13 and D3. While DTR is high, D3 blocks, so the button and R1/C1 work as on Ben's.",
        "Memory map: RAM $0000–$3FFF, VIA $6000–$7FFF, ROM $8000–$FFFF. Writes to $4000–$7FFF also go to the RAM, into its",
        "upper half, which can't be read (A14 drives /OE). +5V comes from the USB serial adapter."], "Notes")
    return s


def io(board, planned):
    s = Sheet(board, "Michael: VIA, LCD, LED, keyboard board and serial (2 of 3)", subtitle(planned), 1300, 980)
    via = {f"P{p}{i}": f"P{p}{i}" for p in "AB" for i in range(8)} | {
        f"RS{i}": f"A{i}" for i in range(4)} | {f"D{i}": f"D{i}" for i in range(8)} | {
        "VSS": "GND", "VDD": "+5V", "IRQB": "IRQB", "RWB": "RWB", "CS2B": "VIA/CS2", "CS1": "A13",
        "PHI2": "PHI2", "RESB": "RESB", "CA2": "CA2", "CB2": "CB2"}
    uses = PLANNED_PORT_A_USES if planned else PORT_A_USES
    if planned:
        via["PA0"] = None
    s.dip("U5", "W65C22S VIA", 390, 110, W65C22, via, width=130, notes=uses | {
        "CA2": "keyboard IRQ", "CB2": "serial in", "CB1": "shift clock out"})

    lcd = [(1, "VSS", "GND"), (2, "VDD", "+5V"), (3, "V0", "V0"), (4, "RS", "PA5"), (5, "RW", "PA6"),
           (6, "E", "PA7")] + [(7 + i, f"DB{i}", f"PB{i}") for i in range(8)] + [(15, "A", "+5V"),
                                                                                 (16, "K", "GND")]
    s.ic("U3", "20×4 LCD (HD44780)", 790, 110, left=lcd, width=110)
    s.pot("RV1", "10 kΩ potentiometer", 860, 490, "+5V", "V0", "GND")

    if planned:   # on PA1, lit while it is high
        s.two_pin("resistor", "R8", "220 Ω", 790, 650, "PA1", "LED")
        s.two_pin("led", "D1", "red LED", 870, 650, "LED", "GND", names=("A", "K"))
    else:         # lit while PA2 is low, so the display's reset (idle high) leaves it dark
        s.two_pin("resistor", "R8", "220 Ω", 790, 650, "+5V", "LED")
        s.two_pin("led", "D1", "red LED", 870, 650, "LED", "PA2", names=("A", "K"))

    kbd = [(1, "VCC", "+5V"), (2, "GND", "GND"), (3, "IRQ", "CA2"), (4, "KBD_CLK_OUT", "PA3"),
           (5, "REG_OE", "PA4"), (6, "DE", "PA5"), (7, "DP", "PA6")] + [
        (8 + i, f"D{7 - i}", f"PB{7 - i}") for i in range(8)]
    s.ic("J1", "keyboard board (its J2)", 1120, 110, left=kbd, width=120,
         caption="michael-bidirectional-PS2-…-v-1.0.pdf")
    serial = {"DTR": "DTR", "TXD": "CB2", "GND": "GND", "+5V": "+5V"}
    s.ic("J2", "USB serial (CP2102)", 1120, 500, left=[(i + 1, n, serial.get(n)) for i, n in enumerate(SERIAL)],
         width=120, caption="powers Michael; DTR resets it (sheet 1)")

    led = ("LED: moved to PA1 in stage 4, the right way round: it lights while PA1 is high, as upload_v3.inc expects." if planned
           else "LED: lit while PA2 is low, because PA2 is also the display's reset (idle high). It goes back to normal "
                "once PA2 is the LED's alone.")
    y = s.note(24, 800, [
        "PORTB is shared by the LCD, the keyboard board (its 74HC595s drive it while SOEB is low; its 74HC165s load it",
        "while SOLB is low) and the FPGA. The keyboard driver saves and restores PORTA, PORTB and their DDRs in its interrupt.",
        "Serial is received only: CB2 is the shift register's input, timed by T2 (firmware/lib/serial/), so CB1 is its clock out.",
        "J1's pins and the PA3–PA6 uses are from base_config_v2.inc, keyboard_driver.inc and the keyboard board's schematic.",
        led, "Ben's buttons SW2–SW6 and their pull-ups R3–R7 are not fitted. The LCD's backlight is straight to +5V and GND."],
        "Notes")
    return s


def fpga(board, planned):
    title = "Michael: FPGA bus interface (3 of 3)" if planned else "Michael: FPGA display interface (3 of 3)"
    s = Sheet(board, title, subtitle(planned) + " U7, U8 and U10 run from +3V3.", 1420, 1080)
    data = {f"B{i + 1}": f"PB{i}" for i in range(8)} | {f"A{i + 1}": f"d[{i}]" for i in range(8)}
    power = {"GND": "GND", "VCC": "+3V3"}
    s.dip("U7", "74LVC245 (data)", 330, 110, LVC245, data | power | (
        {"DIR": "d_dir", "/OE": "d_oeb"} if planned else {"DIR": "GND", "/OE": "GND"}), width=110)
    control = {"B3": "PA2", "B4": "PA5", "B5": "U8.B5", "B8": "U8.B8", "A5": "bl"}
    if planned:   # E now arrives on B3 from PA2; B1 and B2 are tied off
        control |= {"B1": "U8.B1", "B2": "U8.B2", "B6": "PA4", "B7": "PA6",
                    "A1": "pio9", "A2": "pio10", "A3": "e", "A4": "rs", "A6": "soeb", "A7": "rw"}
    else:
        control |= {"B1": "PA0", "B2": "PA1", "B6": "U8.B6", "B7": "U8.B7",
                    "A1": "e", "A2": "csb", "A3": "rstb", "A4": "dc"}
    unused = {"B1": "unused", "B2": "unused", "B5": "unused"} if planned else {}
    s.dip("U8", "74LVC245 (control)", 330, 420, LVC245, control | power | {"DIR": "GND", "/OE": "GND"}, width=110,
          notes=unused)
    s.two_pin("capacitor", "C5", "0.1 µF", 110, 360, "+3V3", "GND", length=70)
    s.two_pin("capacitor", "C6", "0.1 µF", 180, 360, "+3V3", "GND", length=70)
    s.two_pin("resistor", "R9", "10 kΩ", 60, 720, "+3V3", "U8.B5")
    s.text(60, 850, "backlight on", "middle", 10.5, fill=MUTED)
    ties = ([("R12", "U8.B8"), ("R14", "U8.B1"), ("R17", "U8.B2")] if planned
            else [("R10", "U8.B6"), ("R11", "U8.B7"), ("R12", "U8.B8")])
    for i, (ref, net) in enumerate(ties):
        s.two_pin("resistor", ref, "10 kΩ", 130 + i * 70, 720, net, "GND")
    s.text(200, 850, "ties (unused inputs)", "middle", 10.5, fill=MUTED)
    if planned:
        for i, (ref, top, bottom, why) in enumerate((("R18", "PA2", "GND", "E idle low"),
                                                     ("R15", "+3V3", "d_oeb", "off unconfigured"),
                                                     ("R16", "d_dir", "GND", "inward by default"))):
            s.two_pin("resistor", ref, "10 kΩ", 340 + i * 100, 720, top, bottom)
            s.text(340 + i * 100, 850, why, "middle", 10.5, fill=MUTED)

    lcd = ["lcd_cs", "lcd_reset", "lcd_dc", "lcd_mosi", "lcd_sck", "lcd_led", "lcd_miso"]
    cmod = {i + 1: f"d[{i}]" for i in range(8)} | {13: "bl", 24: "VU", 25: "GND"} | {
        26 + i: n for i, n in enumerate(lcd)}
    if planned:
        cmod |= {9: "pio9", 10: "pio10", 11: "e", 12: "rs", 14: "d_oeb", 17: "d_dir", 18: "soeb", 19: "rw"}
    else:
        cmod |= {9: "e", 10: "csb", 11: "rstb", 12: "dc"}
    s.dip("U9", "Cmod A7-35T", 720, 110, CMOD, cmod, width=110,
          notes={"PIO9": "ignored", "PIO10": "ignored", "PIO13": "ignored"} if planned else None,
          caption="33–37 reserved for touch")

    tft = {"GND": "GND", "Vin": "+3V3", "CLK": "lcd_sck", "MISO": "lcd_miso", "MOSI": "lcd_mosi", "CS": "lcd_cs",
           "D/C": "lcd_dc", "RST": "lcd_reset", "Lite": "lcd_led"}
    s.ic("U10", "Adafruit 2.8\" TFT (ILI9341)", 1150, 110, width=130,
         left=[(i + 1, n, tft.get(n) if i != 10 else None) for i, n in enumerate(ADAFRUIT_TFT)],
         caption="capacitive touch version; touch (I²C) not connected")

    s.ic("U11", "LM1117T-3.3", 1150, 700, left=[(3, "IN", "+5V"), (1, "GND", "GND")],
         right=[(2, "OUT", "+3V3")], width=110, caption="tab: OUT")
    s.two_pin("electrolytic", "C8", "10 µF tantalum, to add", 1100, 820, "+5V", "GND")
    s.two_pin("electrolytic", "C9", "10 µF tantalum, to add", 1250, 820, "+3V3", "GND")
    s.two_pin("diode", "D2", "1N4001 (or similar)", 740, 720, "+5V", "VU", names=("A", "K"))
    s.two_pin("electrolytic", "C7", "1 µF 25 V electrolytic", 900, 720, "+5V", "GND")

    notes = ["From ../fpga/spi-display/WIRING.md. The '245s take Michael's 5 V signals on their B side to the Cmod's 3.3 V "
             "A side.",
             "Cmod pins carry the FPGA design's port names (spi-display/constr/cmod_a7.xdc); U10's MISO is read only by the "
             "display probe.",
             "The Cmod runs from Michael's +5V through D2 (band towards the Cmod), so its USB is needed only for programming.",
             "C8 and C9: the 10 µF the LM1117's data sheet asks for on its input and output (for stability). Not fitted "
             "on Michael yet: see the to-do list in README.md."]
    if planned:
        notes[1] = ("The FPGA drives U7's /OE and DIR to read: d_oeb is gated by SOEB in logic, so it never drives "
                    "PORTB with the keyboard board.")
        notes.append("E moves to PA2 in stage 4, through U8's B3 (the old display reset), so it needs no new wire. "
                     "U8's B1, B2 and B5 are ignored.")
        notes.append("RS and RW are the LCD's own register select and read/write pins, with the same meanings. "
                     "The new port names are proposals.")
    else:
        notes[0] += " DIR and /OE are grounded."
    s.note(24, 920, notes, "Notes")
    return s


SHEETS = {"michael-core.svg": core, "michael-io.svg": io, "michael-fpga-display.svg": fpga}


def build(planned=False):
    board = Board()
    return board, {name: draw(board, planned) for name, draw in SHEETS.items()}


def board(planned=False):
    return build(planned)[0]


def parts_list(board, planned):
    """The parts, as a Markdown table."""
    def order(ref):
        letters = ref.rstrip("0123456789")
        return letters, int(ref[len(letters):])
    state = "once the FPGA bus plan is complete (planned)" if planned else "as built (2026-10-03)"
    lines = [f"# Michael's parts, {state}", "",
             "Generated by `michael_schematic.py` from the schematics beside this file. \"(or similar)\" marks a part",
             "identified only from a photo. The keyboard board's own parts are on its schematic,",
             "`michael-bidirectional-PS2-keyboard-interface-schematic-v-1.0.pdf`" + (" (one level up)." if planned else "."),
             "", "| Ref | Part | Sheet |", "|---|---|---|"]
    for ref in sorted(board.parts, key=order):
        sheet = board.sheets[ref].removeprefix("Michael: ")
        lines.append(f"| {ref} | {board.values[ref]} | {sheet} |")
    return "\n".join(lines) + "\n"


def outputs():
    """Both sets of sheets and parts lists by path: as built, then planned/."""
    files = {}
    for planned in (False, True):
        board, drawn = build(planned)
        prefix = "planned/" if planned else ""
        files |= {prefix + name: sheet.svg() for name, sheet in drawn.items()}
        files[prefix + "parts.md"] = parts_list(board, planned)
    return files


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(here, "planned"), exist_ok=True)
    for name, text in outputs().items():
        with open(os.path.join(here, name), "w") as f:
            f.write(text)
