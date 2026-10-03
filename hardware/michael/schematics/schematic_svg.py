"""A small schematic drawer: parts with numbered, named pins, joined by net labels, drawn as SVG.

Every pin that connects ends in a label naming its net, as KiCad's global labels do; pins with the same
label are joined. Drawing a part also records its pins in the Board, so the netlist can be checked
(tools/tests/test_michael_schematic.py) as well as looked at.
"""
from collections import defaultdict
from xml.sax.saxutils import escape

PITCH = 20          # pin spacing
STUB = 26           # pin length outside a part
INK, MUTED, BODY, NOTE = "#1f2328", "#59636e", "#fff8dc", "#9a6700"
POWER = {"+5V": "#b42318", "+3V3": "#bc4c00", "GND": "#1f2328"}
CHAR = 6.3          # average character width at 11 px, for sizing labels


class Board:
    """The netlist: each part's pins as (number, name, net); net None is not connected."""

    def __init__(self):
        self.parts = {}

    def add(self, ref, pins):
        if ref in self.parts:
            raise ValueError(f"{ref} drawn twice")
        self.parts[ref] = pins

    def net(self, ref, pin):
        """The net on a part's pin, by number (int) or name (str)."""
        for number, name, net in self.parts[ref]:
            if pin == (number if isinstance(pin, int) else name):
                return net
        raise KeyError(f"{ref} has no pin {pin}")

    def nets(self):
        found = defaultdict(list)
        for ref, pins in self.parts.items():
            for number, name, net in pins:
                if net is not None:
                    found[net].append(f"{ref}.{number if number is not None else name}")
        return dict(found)


class Sheet:
    def __init__(self, board, title, subtitle, width, height):
        self.board, self.title, self.subtitle = board, title, subtitle
        self.width, self.height = width, height
        self.out = []

    # ---- primitives ---------------------------------------------------------------------------------
    def text(self, x, y, s, anchor="start", size=11, weight="normal", fill=INK, style="normal"):
        self.out.append(f'<text x="{x:g}" y="{y:g}" font-size="{size}" font-weight="{weight}" '
                        f'font-style="{style}" text-anchor="{anchor}" fill="{fill}">{escape(s)}</text>')

    def line(self, x1, y1, x2, y2, color=INK, width=1.3, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.out.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{color}" '
                        f'stroke-width="{width}"{d}/>')

    def path(self, d, fill="none", width=1.3, color=INK):
        self.out.append(f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{width}"/>')

    def rect(self, x, y, w, h, fill=BODY, rx=0, width=1.5, color=INK, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.out.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx}" fill="{fill}" '
                        f'stroke="{color}" stroke-width="{width}"{d}/>')

    def label(self, x, y, net, toward):
        """A net label whose connecting end is at (x, y), extending left, right, up or down from it."""
        if net is None:   # not connected
            self.line(x - 4, y - 4, x + 4, y + 4, MUTED)
            self.line(x - 4, y + 4, x + 4, y - 4, MUTED)
            return
        w, h = len(net) * CHAR + 10, 15
        color = POWER.get(net, INK)
        fill = "#ffffff" if net not in POWER else "#fff1ef" if net != "GND" else "#eaeef2"
        if toward in ("left", "right"):
            x0 = x - w if toward == "left" else x
            self.rect(x0, y - h / 2, w, h, fill, 3, 1, color)
            self.text(x0 + w / 2, y + 4, net, "middle", 10.5, "bold" if net in POWER else "normal", color)
        else:
            y0 = y - h if toward == "up" else y
            self.rect(x - w / 2, y0, w, h, fill, 3, 1, color)
            self.text(x, y0 + 11, net, "middle", 10.5, "bold" if net in POWER else "normal", color)
        return w

    def note(self, x, y, lines, heading=None, color=INK, size=11.5):
        if heading:
            self.text(x, y, heading, size=13, weight="bold")
            y += 20
        for s in lines:
            self.text(x, y, s, size=size, fill=color)
            y += 17
        return y

    # ---- parts --------------------------------------------------------------------------------------
    def ic(self, ref, value, x, y, left=(), right=(), width=120, rows=None, caption=None):
        """A box with pins down each side. left and right list (number, name, net[, note]) top to bottom;
        None leaves a gap. Notes are written beyond the pin's label."""
        rows = rows or max(len(left), len(right))
        h = rows * PITCH + PITCH
        self.rect(x, y, width, h)
        self.text(x + width / 2, y - 22, ref, "middle", 13, "bold")
        self.text(x + width / 2, y - 7, value, "middle", 11, fill=MUTED)
        if caption:
            self.text(x + width / 2, y + h + 16, caption, "middle", 10.5, fill=MUTED, style="italic")
        pins = []
        for side, entries in (("left", left), ("right", right)):
            for i, entry in enumerate(entries):
                if entry is None:
                    continue
                number, name, net = entry[:3]
                note = entry[3] if len(entry) > 3 else None
                py = y + PITCH * (i + 1)
                edge = x if side == "left" else x + width
                end = edge - STUB if side == "left" else edge + STUB
                self.line(edge, py, end, py)
                if number is not None:
                    self.text((edge + end) / 2, py - 3, str(number), "middle", 9.5, fill=MUTED)
                inner = edge + 5 if side == "left" else edge - 5
                self.text(inner, py + 4, name, "start" if side == "left" else "end", 10.5)
                w = self.label(end, py, net, side) or 8
                if note:
                    nx = end - w - 6 if side == "left" else end + w + 6
                    self.text(nx, py + 4, note, "end" if side == "left" else "start", 10, fill=MUTED,
                              style="italic")
                pins.append((number, name, net))
        self.board.add(ref, pins)

    def dip(self, ref, value, x, y, names, nets, width=120, notes=None, caption=None):
        """A DIP package in pin order: 1 to n/2 down the left, n/2 + 1 to n up the right. names lists the
        pin names from pin 1; nets maps names (or numbers) to nets, and unlisted pins are not connected."""
        notes = notes or {}
        n = len(names)

        def entry(i):
            name = names[i]
            net = nets.get(i + 1, nets.get(name))
            return (i + 1, name, net, notes.get(name))

        left = [entry(i) for i in range(n // 2)]
        right = [entry(i) for i in range(n - 1, n // 2 - 1, -1)]
        self.ic(ref, value, x, y, left, right, width, caption=caption)

    def two_pin(self, kind, ref, value, x, y, top, bottom, names=("1", "2"), length=90):
        """A resistor, capacitor, LED, diode, switch or unknown part ('box'), drawn vertically from
        (x, y): pin 1 at the top."""
        mid = y + length / 2
        body = {"resistor": 26, "capacitor": 8, "led": 18, "diode": 18, "switch": 22, "box": 30}[kind]
        self.line(x, y, x, mid - body / 2)
        self.line(x, mid + body / 2, x, y + length)
        if kind == "resistor":
            self.rect(x - 6, mid - 13, 12, 26, "#ffffff", 0, 1.3)
        elif kind == "capacitor":
            self.line(x - 12, mid - 4, x + 12, mid - 4, width=2)
            self.line(x - 12, mid + 4, x + 12, mid + 4, width=2)
        elif kind in ("led", "diode"):   # anode at the top
            self.path(f"M{x - 9:g},{mid - 8:g} L{x + 9:g},{mid - 8:g} L{x:g},{mid + 7:g} Z", "#ffffff")
            self.line(x - 9, mid + 8, x + 9, mid + 8, width=1.6)
            if kind == "led":
                for d in (-3, 4):
                    self.line(x + 11, mid + d, x + 19, mid + d + 6)
                    self.path(f"M{x + 19:g},{mid + d + 6:g} l-4,-1 l2,-3 Z", INK, 1)
        elif kind == "switch":
            self.line(x, mid - 11, x - 9, mid + 9)
            self.line(x - 10, mid - 2, x - 18, mid - 2)
            self.path(f"M{x - 2:g},{mid - 11:g} a2,2 0 1 0 0.1,0", "#ffffff")
            self.path(f"M{x - 2:g},{mid + 11:g} a2,2 0 1 0 0.1,0", "#ffffff")
        elif kind == "box":
            self.rect(x - 14, mid - 15, 28, 30, "#ffffff", 0, 1.3, NOTE, "4 3")
            self.text(x, mid + 5, "?", "middle", 14, "bold", NOTE)
        tx = x + {"led": 24, "box": 22}.get(kind, 16)
        self.text(tx, mid - 2, ref, size=11.5, weight="bold")
        self.text(tx, mid + 12, value, size=10.5, fill=MUTED)
        self.label(x, y, top, "up")
        self.label(x, y + length, bottom, "down")
        self.board.add(ref, [(1, names[0], top), (2, names[1], bottom)])

    def pot(self, ref, value, x, y, top, wiper, bottom, length=90):
        """A potentiometer from (x, y) down, its wiper (pin 2) to the left."""
        mid = y + length / 2
        self.line(x, y, x, mid - 13)
        self.line(x, mid + 13, x, y + length)
        self.rect(x - 6, mid - 13, 12, 26, "#ffffff", 0, 1.3)
        self.line(x - 30, mid, x - 8, mid)
        self.path(f"M{x - 8:g},{mid:g} l-6,-4 l0,8 Z", INK, 1)
        self.text(x + 12, mid - 2, ref, size=11.5, weight="bold")
        self.text(x + 12, mid + 12, value, size=10.5, fill=MUTED)
        self.label(x, y, top, "up")
        self.label(x - 30, mid, wiper, "left")
        self.label(x, y + length, bottom, "down")
        self.board.add(ref, [(1, "1", top), (2, "W", wiper), (3, "3", bottom)])

    def nand(self, x, y, a, b, out):
        """One 74HC00 gate, inputs at the left: a, b and out are (pin, net). Returns the pins for the
        package's netlist entry."""
        self.path(f"M{x:g},{y:g} L{x + 22:g},{y:g} A20,20 0 0 1 {x + 22:g},{y + 40:g} L{x:g},{y + 40:g} Z",
                  BODY, 1.5)
        self.path(f"M{x + 46:g},{y + 20:g} a4,4 0 1 0 0.1,0", "#ffffff")
        pins = []
        for (pin, net), py in ((a, y + 10), (b, y + 30)):
            self.line(x - STUB, py, x, py)
            self.text(x - STUB / 2, py - 3, str(pin), "middle", 9.5, fill=MUTED)
            self.label(x - STUB, py, net, "left")
            pins.append((pin, f"{pin}", net))
        self.line(x + 50, y + 20, x + 50 + STUB, y + 20)
        self.text(x + 50 + STUB / 2, y + 17, str(out[0]), "middle", 9.5, fill=MUTED)
        self.label(x + 50 + STUB, y + 20, out[1], "right")
        pins.append((out[0], f"{out[0]}", out[1]))
        return pins

    # ---- output -------------------------------------------------------------------------------------
    def svg(self):
        head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
                f'viewBox="0 0 {self.width} {self.height}" font-family="Helvetica, Arial, sans-serif">',
                f'<rect width="{self.width}" height="{self.height}" fill="#ffffff"/>',
                f'<text x="24" y="34" font-size="18" font-weight="bold" fill="{INK}">{escape(self.title)}</text>',
                f'<text x="24" y="54" font-size="12" fill="{MUTED}">{escape(self.subtitle)}</text>']
        return "\n".join(head + self.out + ["</svg>"]) + "\n"
