#!/usr/bin/env python3
"""Generate the KiCad schematic of the Antminer BB-Black V1.8 test breakout (cape).

    python gen-sch.py            # writes breakout.kicad_sch + 5 sub-sheets + breakout.kicad_pro
    python check.py              # (after kicad-cli netlist export) compares KiCad's nets with ours

Everything is placed by coordinates on the 1.27 mm grid; parts are connected with real wires
inside a block and with global labels between blocks/sheets. Pin positions come from the
installed KiCad symbol libraries (kisym.py), so the drawing follows the library geometry.
"""
import json
import os
import uuid

import kisym
from kisym import children, child, dump, q, unq

PROJECT = "breakout"
HERE = os.path.dirname(os.path.abspath(__file__))
DATE = "2026-10-06"
ROOT_UUID = "7a1c0b1e-0001-4000-8000-000000000001"

# footprint choices (hand solderable 0805 / SOIC / THT connectors)
FP = {
    "R": "Resistor_SMD:R_0805_2012Metric",
    "R_big": "Resistor_SMD:R_1206_3216Metric",
    "C": "Capacitor_SMD:C_0805_2012Metric",
    "LED": "LED_SMD:LED_0805_2012Metric",
    "pot": "Potentiometer_THT:Potentiometer_Bourns_3386P_Vertical",
    "ntc": "Resistor_SMD:R_0805_2012Metric",
    "pin1x02": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    "pin1x04": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "pin1x10": "Connector_PinHeader_2.54mm:PinHeader_1x10_P2.54mm_Vertical",
    "pin2x09": "Connector_PinHeader_2.54mm:PinHeader_2x09_P2.54mm_Vertical",
    "socket2x23": "Connector_PinSocket_2.54mm:PinSocket_2x23_P2.54mm_Vertical",
    "qwiic": "Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal",
    "term02": "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
    "term03": "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal",
    "term06": "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-6-5.08_1x06_P5.08mm_Horizontal",
    "term10": "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-10-5.08_1x10_P5.08mm_Horizontal",
    "dip8": "Button_Switch_THT:SW_DIP_SPSTx08_Slide_9.78x22.5mm_W7.62mm_P2.54mm",
    "push": "Button_Switch_THT:SW_PUSH_6mm",
    "sj": "Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm",
    "soic20": "Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm",
    "hole": "MountingHole:MountingHole_3.2mm_M3_DIN965",
    "tp": "TestPoint:TestPoint_Pad_D1.5mm",
}


def uid():
    return str(uuid.uuid4())


def f(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def rot_pt(px, py, rot):
    rot %= 360
    if rot == 0:
        return px, py
    if rot == 90:
        return -py, px
    if rot == 180:
        return -px, -py
    return py, -px


GRID = 1.27


def snap(v):
    """KiCad's connection grid is 50 mil; every coordinate we emit sits on it."""
    return round(v / GRID) * GRID


def spt(pt):
    return (snap(pt[0]), snap(pt[1]))


def key(pt):
    return (round(snap(pt[0]) * 100), round(snap(pt[1]) * 100))


class Net:
    """union-find over geometry: our own connectivity model, compared against KiCad's netlist."""
    parent = {}
    pins = []      # (sheet, pt, "REF.pin")
    wires = []     # (sheet, a, b)
    names = []     # (sheet, pt, name)
    junctions = set()

    @classmethod
    def find(cls, k):
        cls.parent.setdefault(k, k)
        while cls.parent[k] != k:
            cls.parent[k] = cls.parent[cls.parent[k]]
            k = cls.parent[k]
        return k

    @classmethod
    def union(cls, a, b):
        ra, rb = cls.find(a), cls.find(b)
        if ra != rb:
            cls.parent[ra] = rb

    @staticmethod
    def on_segment(p, a, b):
        (px, py), (ax, ay), (bx, by) = p, a, b
        if abs((bx - ax) * (py - ay) - (by - ay) * (px - ax)) > 1e-3:
            return False
        return min(ax, bx) - 1e-3 <= px <= max(ax, bx) + 1e-3 and min(ay, by) - 1e-3 <= py <= max(ay, by) + 1e-3

    @classmethod
    def resolve(cls):
        for sheet, a, b in cls.wires:
            cls.union((sheet, key(a)), (sheet, key(b)))
        # wire endpoints landing on another wire connect only through a junction (KiCad rule)
        for sheet, a, b in cls.wires:
            for s2, c, d in cls.wires:
                if s2 != sheet or (a, b) == (c, d):
                    continue
                for p in (a, b):
                    if (sheet, key(p)) in cls.junctions and cls.on_segment(p, c, d):
                        cls.union((sheet, key(p)), (sheet, key(c)))
        # pins and labels lying on a wire (KiCad connects a pin anywhere on a wire segment)
        for sheet, pt, _ in cls.pins + [(s, p, None) for s, p, _n in cls.names]:
            for s2, c, d in cls.wires:
                if s2 == sheet and cls.on_segment(pt, c, d):
                    cls.union((sheet, key(pt)), (sheet, key(c)))
        for sheet, pt, name in cls.names:
            cls.union((sheet, key(pt)), ("net", name))
        groups = {}
        for sheet, pt, ref in cls.pins:
            if ref.startswith("#"):
                continue        # power symbols / flags are not in KiCad's netlist
            groups.setdefault(cls.find((sheet, key(pt))), set()).add(ref)
        named = {}
        for sheet, pt, name in cls.names:
            named[cls.find((sheet, key(pt)))] = name
        return [(named.get(r, ""), sorted(g)) for r, g in groups.items()]


class Sheet:
    counters = {}
    all_sheets = []

    def __init__(self, filename, title, sheet_uuid=None, path=None, paper="A3"):
        self.filename = filename
        self.title = title
        self.uuid = sheet_uuid or uid()
        self.path = path or f"/{ROOT_UUID}"
        self.paper = paper
        self.items = []
        self.libs = {}
        Sheet.all_sheets.append(self)

    # ---- primitives ---------------------------------------------------------------------
    def part(self, lib_id, value, x, y, rot=0, footprint=None, ref=None, ref_at=None, val_at=None,
             hide_ref=False, hide_val=False):
        x, y = snap(x), snap(y)
        sym = kisym.load(lib_id)
        if lib_id not in self.libs:
            flat = ["symbol", q(lib_id)] + sym[2:]
            self.libs[lib_id] = dump(flat, 1)
        props = {unq(p[1]): unq(p[2]) for p in children(sym, "property")}
        prefix = props.get("Reference", "U")
        if ref is None:
            n = Sheet.counters.get(prefix, 0) + 1
            Sheet.counters[prefix] = n
            ref = f"{prefix}{n:02d}" if prefix.startswith("#") else f"{prefix}{n}"
        fp = footprint if footprint is not None else props.get("Footprint", "")
        if ref_at is None:
            ref_at = (x + 2.54, y - 1.27)
        if val_at is None:
            val_at = (x + 2.54, y + 1.27)
        pins = {}
        pin_lines = []
        for num, name, px, py, ang, ln, typ in kisym.pins(sym):
            rx, ry = rot_pt(px, py, rot)
            pt = (x + rx, y - ry)
            pins[num] = pt
            Net.pins.append((self.filename, pt, f"{ref}.{num}"))
            pin_lines.append(f'\t\t(pin "{num}" (uuid "{uid()}"))')

        def prop(name, val, at, hide, justify="left"):
            h = " (hide yes)" if hide else ""
            return (f'\t\t(property "{name}" "{val}" (at {f(at[0])} {f(at[1])} 0)\n'
                    f'\t\t\t(effects (font (size 1.27 1.27)) (justify {justify}){h})\n\t\t)')

        txt = [f'\t(symbol (lib_id "{lib_id}") (at {f(x)} {f(y)} {rot}) (unit 1)',
               '\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)',
               f'\t\t(uuid "{uid()}")',
               prop("Reference", ref, ref_at, hide_ref or prefix.startswith("#")),
               prop("Value", value, val_at, hide_val),
               prop("Footprint", fp, (x, y), True),
               prop("Datasheet", props.get("Datasheet", "~"), (x, y), True),
               prop("Description", props.get("Description", ""), (x, y), True)]
        txt += pin_lines
        txt.append(f'\t\t(instances (project "{PROJECT}" (path "{self.path}" (reference "{ref}") (unit 1))))')
        txt.append("\t)")
        self.items.append("\n".join(txt))
        return Part(ref, pins, value)

    def wire(self, a, b):
        a, b = spt(a), spt(b)
        if key(a) == key(b):
            return
        self.items.append(f'\t(wire (pts (xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])}))\n'
                          f'\t\t(stroke (width 0) (type default)) (uuid "{uid()}")\n\t)')
        Net.wires.append((self.filename, a, b))

    def poly(self, *pts):
        for a, b in zip(pts, pts[1:]):
            self.wire(a, b)
        return pts[-1]

    def junction(self, pt):
        pt = spt(pt)
        Net.junctions.add((self.filename, key(pt)))
        self.items.append(f'\t(junction (at {f(pt[0])} {f(pt[1])}) (diameter 0) (color 0 0 0 0) (uuid "{uid()}"))')

    def nc(self, pt):
        pt = spt(pt)
        self.items.append(f'\t(no_connect (at {f(pt[0])} {f(pt[1])}) (uuid "{uid()}"))')

    def label(self, pt, name, rot=0):
        pt = spt(pt)
        justify = "left" if rot in (0, 90) else "right"
        self.items.append(
            f'\t(global_label "{name}" (shape passive) (at {f(pt[0])} {f(pt[1])} {rot}) (fields_autoplaced yes)\n'
            f'\t\t(effects (font (size 1.27 1.27)) (justify {justify}))\n'
            f'\t\t(uuid "{uid()}")\n'
            f'\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {f(pt[0])} {f(pt[1])} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t\t)\n\t)')
        Net.names.append((self.filename, pt, name))

    def power(self, pt, name, rot=0, lib=None):
        """power symbol with its pin at pt. rot 0: body up (+V) / down (GND); 180: flipped;
        90 / 270: body sideways (used in the header lanes)."""
        pt = spt(pt)
        lib_id = "power:" + (lib or name)
        gndish = name in ("GND", "GNDA")
        if rot == 0:
            va = (pt[0], pt[1] + 3.81) if gndish else (pt[0] + 1.27, pt[1] - 3.81)
        elif rot == 180:
            va = (pt[0], pt[1] - 3.81) if gndish else (pt[0] + 1.27, pt[1] + 3.81)
        else:
            # body points left for (+V rot 90, GND rot 270), right for (+V rot 270, GND rot 90)
            left = (rot == 90) != gndish
            va = (pt[0] - 6.35, pt[1]) if left else (pt[0] + 6.35, pt[1])
        p = self.part(lib_id, name, pt[0], pt[1], rot, footprint="", val_at=va)
        Net.names.append((self.filename, pt, name))
        return p

    def power_side(self, pt, dx, name, lib=None):
        """wire from a pin sideways by dx and a power symbol lying in the same lane, pointing away."""
        end = (pt[0] + dx, pt[1])
        self.wire(pt, end)
        gndish = name in ("GND", "GNDA")
        rot = (270 if gndish else 90) if dx < 0 else (90 if gndish else 270)
        return self.power(end, name, rot, lib)

    def flag(self, pt):
        p = self.part("power:PWR_FLAG", "PWR_FLAG", pt[0], pt[1], 0, footprint="", val_at=(pt[0], pt[1] - 5.08))
        return p

    def text(self, pt, s, size=1.27, bold=False):
        b = " (bold yes)" if bold else ""
        self.items.append(f'\t(text "{s}" (exclude_from_sim no) (at {f(pt[0])} {f(pt[1])} 0)\n'
                          f'\t\t(effects (font (size {size} {size}){b}) (justify left bottom))\n'
                          f'\t\t(uuid "{uid()}")\n\t)')

    def sheet_symbol(self, x, y, w, h, name, filename, sheet_uuid, page):
        self.items.append(
            f'\t(sheet (at {f(x)} {f(y)}) (size {f(w)} {f(h)}) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
            f'\t\t(fields_autoplaced yes) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000))\n'
            f'\t\t(uuid "{sheet_uuid}")\n'
            f'\t\t(property "Sheetname" "{name}" (at {f(x)} {f(y - 0.7)} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n\t\t)\n'
            f'\t\t(property "Sheetfile" "{filename}" (at {f(x)} {f(y + h + 0.6)} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (justify left top))\n\t\t)\n'
            f'\t\t(instances (project "{PROJECT}" (path "/{ROOT_UUID}" (page "{page}"))))\n\t)')

    # ---- helpers ------------------------------------------------------------------------
    def stub_label(self, pt, dx, name, dy=0):
        """wire from pt by (dx, dy), global label at the end (text away from the pin)."""
        end = (pt[0] + dx, pt[1] + dy)
        self.wire(pt, end)
        if dy:
            rot = 90 if dy < 0 else 270
        else:
            rot = 0 if dx > 0 else 180
        self.label(end, name, rot)
        return end

    def stub_power(self, pt, dx, dy, name, rot=0, lib=None):
        end = (pt[0] + dx, pt[1] + dy)
        self.wire(pt, end)
        self.power(end, name, rot, lib)
        return end

    def write(self, root=False):
        lines = [f'(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0")',
                 f'\t(uuid "{self.uuid}")', f'\t(paper "{self.paper}")',
                 f'\t(title_block (title "{self.title}") (date "{DATE}") (rev "A")\n'
                 f'\t\t(company "Antminer BB-Black V1.8 I/O module") (comment 1 "generated by hardware/breakout/gen-sch.py")\n\t)',
                 "\t(lib_symbols"]
        for lib_id in sorted(self.libs):
            lines.append("\t\t" + self.libs[lib_id])
        lines.append("\t)")
        lines += self.items
        if root:
            lines.append('\t(sheet_instances (path "/" (page "1")))')
        lines.append("\t(embedded_fonts no)")
        lines.append(")")
        with open(os.path.join(HERE, self.filename), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")


class Part:
    def __init__(self, ref, pins, value):
        self.ref, self.pins, self.value = ref, pins, value

    def pin(self, num):
        return self.pins[str(num)]


# =========================================================================================
# the design
# =========================================================================================
G = 2.54

# BeagleBone header pin -> net on this breakout. "NC" = not used here (NAND / free), power nets
# are routed to power symbols, everything else becomes a global label.
P9 = {1: "GND", 2: "GND", 3: "+3V3", 4: "+3V3", 5: "NC", 6: "NC", 7: "+5V", 8: "+5V", 9: "NC",
      10: "SYS_RESETn", 11: "NC", 12: "GPIO1_28", 13: "NC", 14: "PWM1A", 15: "GPIO1_16", 16: "PWM1B",
      17: "RS485_DE0", 18: "RS485_DE1", 19: "I2C2_SCL", 20: "I2C2_SDA", 21: "UART2_TXD", 22: "UART2_RXD",
      23: "BTN", 24: "UART1_TXD", 25: "GPIO3_21", 26: "UART1_RXD", 27: "GPIO3_19", 28: "NC",
      29: "PWM0B", 30: "FAN_TACH", 31: "NC", 32: "VDD_ADC", 33: "AIN4", 34: "GNDA", 35: "AIN6",
      36: "AIN5", 37: "AIN2", 38: "AIN3", 39: "AIN0", 40: "AIN1", 41: "NC", 42: "GPIO0_7",
      43: "GND", 44: "GND", 45: "GND", 46: "GND"}
P8 = {1: "GND", 2: "GND", 11: "GPIO1_13", 12: "GPIO1_12",
      27: "Q4", 28: "Q5", 29: "Q6", 30: "Q7", 31: "I4", 32: "I5", 33: "I6", 34: "I7",
      37: "UART5_TXD", 38: "UART5_RXD", 39: "I0", 40: "I1", 41: "I2", 42: "I3",
      43: "Q0", 44: "Q1", 45: "Q2", 46: "Q3"}
for _n in range(1, 47):
    P8.setdefault(_n, "NC")
POWER_NETS = {"GND": ("GND", None), "GNDA": ("GNDA", None), "+3V3": ("+3V3", None), "+5V": ("+5V", None),
              "VDD_ADC": ("VDD_ADC", "+1V8"), "+24V": ("+24V", None)}

SUBSHEETS = [  # (name, file, uuid)
    ("outputs", "outputs.kicad_sch", "7a1c0b1e-0002-4000-8000-000000000002"),
    ("inputs", "inputs.kicad_sch", "7a1c0b1e-0003-4000-8000-000000000003"),
    ("analog", "analog.kicad_sch", "7a1c0b1e-0004-4000-8000-000000000004"),
    ("serial", "serial.kicad_sch", "7a1c0b1e-0005-4000-8000-000000000005"),
    ("i2c_pwm", "i2c_pwm.kicad_sch", "7a1c0b1e-0006-4000-8000-000000000006"),
]


def header(sh, x, y, ref, nets, title):
    """2x23 BeagleBone header: odd pins left, even pins right; nets -> labels / power / NC."""
    j = sh.part("Connector_Generic:Conn_02x23_Odd_Even", title, x, y, 0, footprint=FP["socket2x23"],
                ref=ref, ref_at=(x - 1.27, y - 31.75), val_at=(x - 1.27, y + 31.75))
    sh.text((x - 20, y - 33), f"{ref}: BeagleBone-compatible header of the Antminer board", 1.5, True)
    for n in range(1, 47):
        pt = j.pin(n)
        net = nets[n]
        dx = -7.62 if n % 2 else 7.62
        if net == "NC":
            sh.nc(pt)
        elif net in POWER_NETS:
            name, lib = POWER_NETS[net]
            sh.power_side(pt, dx, name, lib)      # symbol lies in the pin's own lane
        else:
            sh.stub_label(pt, dx, net)
    return j


def root_sheet():
    sh = Sheet("breakout.kicad_sch", "Antminer BB-Black V1.8 test breakout - headers and power",
               sheet_uuid=ROOT_UUID)
    header(sh, 60, 100, "P9", P9, "P9")
    header(sh, 150, 100, "P8", P8, "P8")
    sh.text((40, 150), "P8.3-10, P8.22-26, P9.11, P9.13: NAND (do not use). Other NC pins are free, see mainline/pinmux.", 1.27)

    # ---- 24 V field supply input --------------------------------------------------------
    x, y = 250, 60
    sh.text((x - 5, y - 8), "24 V field supply (sensors, output loads). Common GND with the board.", 1.5, True)
    j = sh.part("Connector:Screw_Terminal_01x02", "24V IN", x, y, 0, footprint=FP["term02"],
                ref_at=(x + 2.54, y - 5.08), val_at=(x + 2.54, y + 5.08))
    p24 = sh.poly(j.pin(1), (x - 10.16, y), (x - 10.16, y - 7.62))
    sh.power(p24, "+24V")
    gnd = sh.poly(j.pin(2), (x - 15.24, y + 2.54), (x - 15.24, y + 10.16))
    sh.power(gnd, "GND")
    # TVS across the input, 24 V indicator LED
    d = sh.part("Diode:SMAJ24A", "SMAJ24A", x - 12.7, y - 7.62 + 0, 270, ref_at=(x - 19, y - 9), val_at=(x - 19, y - 6.5))
    # SMAJ24A rot 270: pin A1 at (X, Y-3.81)... connect A1 -> +24V node, A2 -> GND node
    sh.wire(d.pin(1), (d.pin(1)[0], y - 7.62)); sh.wire((d.pin(1)[0], y - 7.62), p24)
    sh.junction(p24)
    sh.poly(d.pin(2), (d.pin(2)[0], y + 2.54), (x - 15.24, y + 2.54))
    sh.junction((x - 15.24, y + 2.54))
    r = sh.part("Device:R", "4.7k", x - 25.4, y - 1.27, 0, footprint=FP["R"], ref_at=(x - 23.5, y - 2.5), val_at=(x - 23.5, y))
    sh.wire(r.pin(1), (x - 25.4, y - 7.62)); sh.wire((x - 25.4, y - 7.62), (d.pin(1)[0], y - 7.62))
    sh.junction((d.pin(1)[0], y - 7.62))
    led = sh.part("Device:LED", "24V", x - 25.4, y + 6.35, 270, footprint=FP["LED"], ref_at=(x - 23.5, y + 5), val_at=(x - 23.5, y + 7.5))
    # LED rot 270: A (pin2) at top (Y-3.81), K (pin1) at bottom (Y+3.81)
    sh.wire(r.pin(2), led.pin(2))
    sh.poly(led.pin(1), (x - 25.4, y + 12.7), (x - 15.24, y + 12.7)); sh.junction(gnd) if False else None
    sh.wire((x - 15.24, y + 12.7), gnd)
    sh.junction(gnd)

    # ---- power flags, test points, LEDs ---------------------------------------------------
    x, y = 250, 110
    sh.text((x - 5, y - 8), "Board rails from P9 (3V3 max ~250 mA, SYS_5V, VDD_ADC 1.8 V). Flags tell ERC these are sources.", 1.5, True)
    for i, (name, lib) in enumerate((("+3V3", None), ("+5V", None), ("VDD_ADC", "+1V8"), ("+24V", None))):
        px = x + i * 20.32
        sh.power((px, y), name, 0, lib)
        sh.wire((px, y), (px + 5.08, y)); sh.flag((px + 5.08, y))
        tp = sh.part("Connector:TestPoint", "TP_" + name.strip("+"), px + 10.16, y, 0, footprint=FP["tp"],
                     ref_at=(px + 8, y - 5), val_at=(px + 8, y - 2.5), hide_val=True)
        sh.wire((px + 5.08, y), tp.pin(1)); sh.junction((px + 5.08, y))
    for i, name in enumerate(("GND", "GNDA")):
        px = x + i * 20.32
        sh.power((px, y + 15.24), name)
        sh.wire((px, y + 15.24), (px + 5.08, y + 15.24)); sh.flag((px + 5.08, y + 15.24))
        tp = sh.part("Connector:TestPoint", "TP_" + name, px + 10.16, y + 15.24, 0, footprint=FP["tp"],
                     ref_at=(px + 8, y + 10), val_at=(px + 8, y + 12.5), hide_val=True)
        sh.wire((px + 5.08, y + 15.24), tp.pin(1)); sh.junction((px + 5.08, y + 15.24))
    # 3V3 indicator
    px = x + 50.8
    sh.power((px, y + 15.24), "+3V3")
    r = sh.part("Device:R", "1k", px, y + 19.05 + 0, 0, footprint=FP["R"], ref_at=(px + 2, y + 17.8), val_at=(px + 2, y + 20.3))
    sh.wire((px, y + 15.24), r.pin(1))
    led = sh.part("Device:LED", "3V3", px, y + 26.67, 270, footprint=FP["LED"], ref_at=(px + 2, y + 25.4), val_at=(px + 2, y + 27.9))
    sh.wire(r.pin(2), led.pin(2))
    sh.stub_power(led.pin(1), 0, G, "GND")

    # ---- reset button (the board has none) ---------------------------------------------
    x, y = 250, 160
    sh.text((x - 5, y - 8), "SYS_RESETn (P9.10): the Antminer board has no reset button.", 1.5, True)
    sw = sh.part("Switch:SW_Push", "RESET", x, y, 0, footprint=FP["push"], ref_at=(x - 2.5, y - 4), val_at=(x - 2.5, y - 1.5))
    sh.stub_label(sw.pin(1), -7.62, "SYS_RESETn")
    sh.stub_power(sw.pin(2), 5.08, 0, "GND")

    # ---- spare GPIO header ---------------------------------------------------------------
    x, y = 330, 100
    sh.text((x - 5, y - 16), "Spare free pins (GPIO / eHRPWM1) for experiments", 1.5, True)
    j = sh.part("Connector:Conn_01x10_Pin", "SPARE", x, y, 0, footprint=FP["pin1x10"],
                ref_at=(x - 1.27, y - 14), val_at=(x - 1.27, y + 14))
    spare = ["GPIO1_28", "PWM1A", "GPIO1_16", "PWM1B", "GPIO3_21", "GPIO3_19", "GPIO0_7", "GPIO1_13", "GPIO1_12"]
    for i, name in enumerate(spare, 1):
        sh.stub_label(j.pin(i), 7.62, name)
    sh.stub_power(j.pin(10), 7.62, 0, "GND")

    # ---- mounting holes ------------------------------------------------------------------
    for i in range(4):   # references MH1..MH4 match the BeagleBone cape template PCB
        sh.part("Mechanical:MountingHole", "M3", 330 + i * 12.7, 160, 0, footprint=FP["hole"], ref=f"MH{i + 1}",
                ref_at=(330 + i * 12.7 - 2, 164), val_at=(330 + i * 12.7 - 2, 166.5), hide_val=True)
    sh.text((325, 170), "4x M3, BeagleBone cape pattern", 1.27)

    # ---- sub sheets ----------------------------------------------------------------------
    for i, (name, fn, su) in enumerate(SUBSHEETS):
        sh.sheet_symbol(30 + i * 60, 220, 45, 25, name, fn, su, str(i + 2))
    sh.text((30, 212), "Sub-sheets, connected with global labels (Q*, I*, AIN*, UART*, I2C2_*, PWM0B, BTN, FAN_TACH)", 1.5, True)
    return sh


def outputs_sheet(su):
    sh = Sheet("outputs.kicad_sch", "Digital outputs Q0..Q7: low-side MOSFET to 24 V loads + LED buffer",
               sheet_uuid=su, path=f"/{ROOT_UUID}/{su}")
    sh.text((20, 20), "Q0..Q3 = P8.43..46 (default profile), Q4..Q7 = P8.27..30. Gate pull-down keeps the load off while the pad is a pull-down input during boot.", 1.5, True)
    for n in range(8):
        ox = 25 + (n % 4) * 55
        oy = 50 + (n // 4) * 50
        sh.text((ox - 5, oy - 25), f"channel {n}", 1.27, True)
        lbl = (ox, oy)
        sh.label(lbl, f"Q{n}", 180)
        qf = sh.part("Transistor_FET:AO3400A", "AO3400A", ox + 20.32, oy, 0, ref_at=(ox + 25.4, oy + 2.5), val_at=(ox + 25.4, oy + 5))
        sh.wire(lbl, qf.pin(1))
        r = sh.part("Device:R", "100k", ox + 7.62, oy + 7.62, 0, footprint=FP["R"], ref_at=(ox + 9.5, oy + 6), val_at=(ox + 9.5, oy + 8.5))
        sh.wire((ox + 7.62, oy), r.pin(1)); sh.junction((ox + 7.62, oy))
        sh.power(r.pin(2), "GND")
        sh.stub_power(qf.pin(2), 0, 5.08, "GND")
        top = (qf.pin(3)[0], oy - 12.7)
        sh.wire(qf.pin(3), top)
        d = sh.part("Diode:SS14", "SS14", ox + 30.48, oy - 12.7, 180, ref_at=(ox + 27.5, oy - 17.5), val_at=(ox + 27.5, oy - 15))
        # rot 180: A (pin2) at left, K (pin1) at right
        sh.wire(top, d.pin(2)); sh.junction(top)
        sh.stub_power(d.pin(1), 5.08, 0, "+24V")
        sh.stub_label(top, 0, f"OUT{n}", dy=-7.62)

    # LED buffer
    ux, uy = 265, 120
    sh.text((ux - 20, uy - 30), "Status LEDs via 74AHCT541 (5 V supply, TTL-level inputs accept 3.3 V)", 1.27, True)
    u = sh.part("74xx:74AHCT541", "74AHCT541", ux, uy, 0, footprint=FP["soic20"], ref_at=(ux + 3, uy - 25.5), val_at=(ux - 20, uy - 25.5))
    sh.text((ux + 15, uy - 18), "R11-R18 470R, D12-D19 LEDs (references hidden, see BOM)", 1.0)
    for n in range(8):
        sh.stub_label(u.pin(2 + n), -7.62, f"Q{n}")
        ypin = u.pin(18 - n)[1]
        r = sh.part("Device:R", "470", ux + 21.59, ypin, 90, footprint=FP["R"], ref_at=(ux + 19.5, ypin - 2.8), val_at=(ux + 23.5, ypin - 2.8), hide_val=(n > 0), hide_ref=(n > 0))
        sh.wire(u.pin(18 - n), r.pin(1))
        led = sh.part("Device:LED", f"Q{n}", ux + 29.21, ypin, 180, footprint=FP["LED"], ref_at=(ux + 27.5, ypin - 2.8), val_at=(ux + 33, ypin - 2.8), hide_val=True, hide_ref=(n > 0))
        # rot 180: A (pin2) left, K (pin1) right
        sh.wire(led.pin(1), (ux + 36.83, ypin))
        if n:
            sh.junction((ux + 36.83, ypin))
    sh.wire((ux + 36.83, u.pin(18)[1]), (ux + 36.83, u.pin(11)[1] + 5.08))
    sh.power((ux + 36.83, u.pin(11)[1] + 5.08), "GND")
    g = (ux - 17.78, u.pin(19)[1])
    sh.wire(u.pin(1), (ux - 17.78, u.pin(1)[1])); sh.wire(u.pin(19), g); sh.wire((ux - 17.78, u.pin(1)[1]), (g[0], g[1] + 5.08))
    sh.junction(g)
    sh.power((g[0], g[1] + 5.08), "GND")
    vcc = (ux, u.pin(20)[1] - 2.54)
    sh.wire(u.pin(20), vcc); sh.power(vcc, "+5V")
    c = sh.part("Device:C", "100n", ux + 10.16, vcc[1] + 3.81, 0, footprint=FP["C"], ref_at=(ux + 12, vcc[1] + 2.5), val_at=(ux + 12, vcc[1] + 5))
    sh.wire(vcc, c.pin(1)); sh.junction(vcc)
    sh.power(c.pin(2), "GND")
    sh.power(u.pin(10), "GND")

    # terminal
    tx, ty = 350, 60
    sh.text((tx - 15, ty - 20), "Loads between +24V and OUTn (max 1 A each, 24 V). SS14 clamps inductive loads.", 1.27, True)
    j = sh.part("Connector:Screw_Terminal_01x10", "OUT0-7 24V GND", tx, ty, 0, footprint=FP["term10"], ref_at=(tx + 2.54, ty - 15), val_at=(tx + 2.54, ty + 16))
    for n in range(8):
        sh.stub_label(j.pin(n + 1), -7.62, f"OUT{n}")
    sh.power_side(j.pin(9), -7.62, "+24V")
    sh.power_side(j.pin(10), -7.62, "GND")
    return sh


def inputs_sheet(su):
    sh = Sheet("inputs.kicad_sch", "Digital inputs I0..I7: DIP switch and 24 V optocoupler inputs in parallel",
               sheet_uuid=su, path=f"/{ROOT_UUID}/{su}")
    sh.text((20, 20), "I0..I3 = P8.39..42 (default profile), I4..I7 = P8.31..34. The SoC pull-up (profile: pull: up) is the only pull-up; switch or optocoupler pull the pad to GND.", 1.5, True)
    for n in range(8):
        ox = 30 + (n % 2) * 95
        oy = 45 + (n // 2) * 30
        sh.text((ox - 5, oy - 8), f"channel {n}: 24 V input IN{n} (PNP/NPN sensor or contact to +24V), common IN_COM", 1.27, True)
        a = (ox, oy)
        sh.label(a, f"IN{n}", 180)
        r = sh.part("Device:R", "4.7k", ox + 8.89, oy, 90, footprint=FP["R_big"], ref_at=(ox + 6.5, oy - 4.5), val_at=(ox + 6.5, oy - 2))
        sh.wire(a, r.pin(1))
        oc = sh.part("Isolator:PC817", "PC817", ox + 25.4, oy + 2.54, 0, ref_at=(ox + 21, oy - 4), val_at=(ox + 21, oy + 9.5))
        sh.wire(r.pin(2), oc.pin(1))
        # cathode node, reverse diode
        cat = sh.poly(oc.pin(2), (ox + 10.16, oy + 5.08))
        d = sh.part("Diode:1N4148W", "1N4148W", ox + 10.16, oy + 1.27, 270, ref_at=(ox + 11.5, oy), val_at=(ox + 11.5, oy + 2.5))
        # rot 270: K (pin1) top at Y-3.81, A (pin2) bottom at Y+3.81
        sh.junction(cat)
        sh.poly(d.pin(1), (ox + 15.24, oy - 2.54), (ox + 15.24, oy))
        sh.junction((ox + 15.24, oy))
        sh.stub_label(cat, -5.08, "IN_COM")
        # transistor side
        sh.stub_label(oc.pin(4), 7.62, f"I{n}")
        sh.stub_power(oc.pin(3), 0, 5.08, "GND")

    # DIP switch: pins 1..8 to I0..I7, 9..16 to GND
    sx, sy = 245, 80
    sh.text((sx - 15, sy - 16), "DIP switch: closes In to GND (simulates a contact)", 1.27, True)
    sw = sh.part("Switch:SW_DIP_x08", "DIP8", sx, sy, 0, footprint=FP["dip8"], ref_at=(sx - 4, sy - 13), val_at=(sx - 4, sy + 13))
    for n in range(8):
        sh.stub_label(sw.pin(n + 1), -5.08, f"I{n}")
        sh.wire(sw.pin(9 + n), (sx + 12.7, sw.pin(9 + n)[1]))
        if n < 7:
            sh.junction((sx + 12.7, sw.pin(9 + n)[1]))
    sh.wire((sx + 12.7, sw.pin(16)[1]), (sx + 12.7, sw.pin(9)[1] + 5.08))
    sh.power((sx + 12.7, sw.pin(9)[1] + 5.08), "GND")
    # push button on I4
    bx, by = 245, 120
    sh.text((bx - 15, by - 6), "Push button on I4 for pulse / counter tests", 1.27, True)
    b = sh.part("Switch:SW_Push", "I4", bx, by, 0, footprint=FP["push"], ref_at=(bx - 2.5, by - 4), val_at=(bx - 2.5, by - 1.5), hide_val=True)
    sh.stub_label(b.pin(1), -5.08, "I4")
    sh.stub_power(b.pin(2), 5.08, 0, "GND")

    # terminal
    tx, ty = 350, 80
    sh.text((tx - 15, ty - 20), "IN0..7: 24 V inputs (approx. 5 mA at 24 V), IN_COM: return, +24V: sensor supply", 1.27, True)
    j = sh.part("Connector:Screw_Terminal_01x10", "IN0-7 COM 24V", tx, ty, 0, footprint=FP["term10"], ref_at=(tx + 2.54, ty - 15), val_at=(tx + 2.54, ty + 16))
    for n in range(8):
        sh.stub_label(j.pin(n + 1), -7.62, f"IN{n}")
    sh.stub_label(j.pin(9), -7.62, "IN_COM")
    sh.power_side(j.pin(10), -7.62, "+24V")
    return sh


def analog_sheet(su):
    sh = Sheet("analog.kicad_sch", "Analog inputs AIN0..AIN6 (1.8 V, 12 bit): protection and test sources",
               sheet_uuid=su, path=f"/{ROOT_UUID}/{su}")
    sh.text((20, 20), "Every channel: 1k series + BAT54S clamp to VDD_ADC/GNDA + 100 nF. Source impedance stays below 10k (AM335x ADC sample time).", 1.5, True)
    kinds = ["pot", "pot", "volt", "volt", "curr", "curr", "ntc"]
    titles = {"pot": "10k pot 0..1.8 V", "volt": "0-10 V in (47k/10k)", "curr": "4-20 mA in (82R)", "ntc": "NTC 10k vs 10k"}
    for n, kind in enumerate(kinds):
        ox, oy = 40 + n * 50, 110
        sh.text((ox - 15, oy - 32), f"AIN{n}: {titles[kind]}", 1.27, True)
        # protection chain, signal flows down from S=(ox,oy)
        S = (ox, oy)
        r = sh.part("Device:R", "1k", ox, oy + 6.35, 0, footprint=FP["R"], ref_at=(ox + 2, oy + 5), val_at=(ox + 2, oy + 7.5))
        sh.wire(S, r.pin(1))
        N = (ox, oy + 12.7)
        sh.wire(r.pin(2), N)
        d = sh.part("Diode:BAT54S", "BAT54S", ox - 5.08, oy + 12.7, 90, ref_at=(ox - 13, oy + 10), val_at=(ox - 13, oy + 12.5))
        # rot 90: K (pin2) top, A (pin1) bottom, COM (pin3) right at (ox, oy+12.7)
        sh.power(d.pin(2), "VDD_ADC", 0, "+1V8")
        sh.power(d.pin(1), "GNDA")
        sh.junction(N)
        T = (ox, oy + 17.78)
        sh.wire(N, T)
        c = sh.part("Device:C", "100n", ox + 8.89, oy + 17.78, 90, footprint=FP["C"], ref_at=(ox + 6.5, oy + 21), val_at=(ox + 6.5, oy + 23.5))
        sh.wire(T, c.pin(1)); sh.junction(T)
        sh.stub_power(c.pin(2), 2.54, 0, "GNDA")
        end = sh.poly(T, (ox, oy + 22.86), (ox + 5.08, oy + 22.86))
        sh.label(end, f"AIN{n}", 0)
        # sources above S
        if kind == "pot":
            rv = sh.part("Device:R_Potentiometer", "10k", ox - 10.16, oy - 7.62, 0, footprint=FP["pot"], ref_at=(ox - 19, oy - 9), val_at=(ox - 19, oy - 6.5))
            sh.power(rv.pin(1), "VDD_ADC", 0, "+1V8")
            sh.power(rv.pin(3), "GNDA")
            sh.poly(rv.pin(2), (ox, oy - 7.62), S)
        elif kind in ("volt", "curr", "ntc"):
            low = sh.part("Device:R", "10k" if kind != "curr" else "82R", ox + 8.89, oy - 5.08, 90,
                          footprint=FP["R"] if kind != "curr" else FP["R_big"], ref_at=(ox + 6.5, oy - 9.5), val_at=(ox + 6.5, oy - 7))
            sh.wire((ox, oy - 5.08), low.pin(1)); sh.junction((ox, oy - 5.08))
            sh.stub_power(low.pin(2), 2.54, 0, "GNDA")
            if kind == "volt":
                top = sh.part("Device:R", "47k", ox, oy - 11.43, 0, footprint=FP["R"], ref_at=(ox + 2, oy - 12.5), val_at=(ox + 2, oy - 10))
                sh.wire(top.pin(2), S)
                e = sh.poly(top.pin(1), (ox, oy - 17.78), (ox - 5.08, oy - 17.78))
                sh.label(e, f"VIN{n}", 180)
            elif kind == "curr":
                e = sh.poly(S, (ox, oy - 7.62), (ox - 5.08, oy - 7.62))
                sh.label(e, f"IIN{n}", 180)
            else:
                th = sh.part("Device:Thermistor_NTC", "10k NTC", ox, oy - 11.43, 0, footprint=FP["ntc"], ref_at=(ox + 2, oy - 12.5), val_at=(ox + 2, oy - 10))
                sh.wire(th.pin(2), S)
                sh.power(th.pin(1), "VDD_ADC", 0, "+1V8")
    # terminal
    tx, ty = 395, 110
    sh.text((tx - 30, ty - 16), "Analog terminal: 0-10 V (VIN2/3), 4-20 mA (IIN4/5), AGND", 1.27, True)
    j = sh.part("Connector:Screw_Terminal_01x06", "VIN IIN AGND", tx, ty, 0, footprint=FP["term06"], ref_at=(tx + 2.54, ty - 8), val_at=(tx + 2.54, ty + 9))
    for i, name in enumerate(("VIN2", "VIN3", "IIN4", "IIN5"), 1):
        sh.stub_label(j.pin(i), -7.62, name)
    sh.wire(j.pin(5), (tx - 10.16, j.pin(5)[1])); sh.wire(j.pin(6), (tx - 10.16, j.pin(6)[1]))
    sh.wire((tx - 10.16, j.pin(5)[1]), (tx - 10.16, j.pin(6)[1] + 2.54)); sh.junction((tx - 10.16, j.pin(6)[1]))
    sh.power((tx - 10.16, j.pin(6)[1] + 2.54), "GNDA")
    return sh


def rs485_block(sh, ox, oy, ch, uart):
    sh.text((ox + 5, oy - 40), f"RS-485 channel {ch}: UART{uart} + RS485_DE{ch} (DE/~RE), 3.3 V transceiver, 120R termination and bias on jumpers", 1.27, True)
    u = sh.part("Interface_UART:THVD1500", "THVD1500", ox + 30.48, oy, 0, ref_at=(ox + 33, oy - 12), val_at=(ox + 33, oy + 12))
    sh.stub_label(u.pin(1), -5.08, f"UART{uart}_RXD")
    sh.stub_label(u.pin(4), -5.08, f"UART{uart}_TXD")
    de = (ox + 17.78, oy)
    sh.poly(u.pin(2), (ox + 17.78, oy - 2.54), de)
    sh.wire(u.pin(3), de); sh.junction(de)
    sh.stub_label(de, -5.08, f"RS485_DE{ch}")
    vcc = (ox + 30.48, oy - 17.78)
    sh.wire(u.pin(8), vcc); sh.power(vcc, "+3V3"); sh.junction(vcc)
    c = sh.part("Device:C", "100n", ox + 22.86, oy - 13.97, 0, footprint=FP["C"], ref_at=(ox + 24.5, oy - 15), val_at=(ox + 24.5, oy - 12.5))
    sh.wire(vcc, c.pin(1)); sh.power(c.pin(2), "GND")
    sh.power(u.pin(5), "GND")
    # activity LEDs: lit while the line is low. Chain R -> LED(K..A) -> +3V3, vertical, pins touching.
    for pin, yoff, rot in ((1, -1, 90), (4, 1, 270)):
        tap = (ox + 17.78, u.pin(pin)[1])
        sh.junction(tap)
        ry = tap[1] + yoff * 3.81
        r = sh.part("Device:R", "1k", ox + 17.78, ry, 0, footprint=FP["R"], ref_at=(ox + 19.5, ry - 1.2), val_at=(ox + 19.5, ry + 1.3))
        ly = tap[1] + yoff * 11.43
        led = sh.part("Device:LED", "RX" if pin == 1 else "TX", ox + 17.78, ly, rot, footprint=FP["LED"], ref_at=(ox + 19.5, ly - 1.2), val_at=(ox + 19.5, ly + 1.3))
        # R rot 0: pin1 top, pin2 bottom. LED rot 90: K (1) bottom, A (2) top; rot 270: K top, A bottom
        assert key(r.pin(2) if yoff < 0 else r.pin(1)) == key(tap), "resistor must touch the tap"
        assert key(r.pin(1) if yoff < 0 else r.pin(2)) == key(led.pin(1)), "LED cathode must touch the resistor"
        sh.power(led.pin(2), "+3V3", 0 if yoff < 0 else 180)
    # bus side
    yA = oy - 7.62
    yB = oy + 10.16
    x1, x2 = ox + 50.8, ox + 58.42
    sh.wire(u.pin(6), (ox + 68.58, yA))
    sh.poly(u.pin(7), (ox + 44.45, oy - 2.54), (ox + 44.45, yB), (ox + 63.5, yB), (ox + 63.5, oy - 5.08), (ox + 68.58, oy - 5.08))
    # bias A: +3V3 -> JP -> 680 -> A
    jp = sh.part("Jumper:Jumper_2_Open", "BIAS_A", x1, yA - 12.7, 90, footprint=FP["pin1x02"], ref_at=(x1 + 2, yA - 14), val_at=(x1 + 2, yA - 11.5))
    r = sh.part("Device:R", "680", x1, yA - 3.81, 0, footprint=FP["R"], ref_at=(x1 + 2, yA - 5), val_at=(x1 + 2, yA - 2.5))
    sh.power(jp.pin(2) if jp.pin(2)[1] < jp.pin(1)[1] else jp.pin(1), "+3V3")
    sh.wire(r.pin(2), (x1, yA)); sh.junction((x1, yA))
    # termination: A -> JP -> 120 -> B
    jp = sh.part("Jumper:Jumper_2_Open", "TERM", x1, yA + 5.08, 90, footprint=FP["pin1x02"], ref_at=(x1 + 2, yA + 3.8), val_at=(x1 + 2, yA + 6.3))
    r = sh.part("Device:R", "120", x1, yA + 13.97, 0, footprint=FP["R"], ref_at=(x1 + 2, yA + 12.7), val_at=(x1 + 2, yA + 15.2))
    sh.junction((x1, yB))
    # bias B: B -> JP -> 680 -> GND
    jp = sh.part("Jumper:Jumper_2_Open", "BIAS_B", x2, yB + 5.08, 90, footprint=FP["pin1x02"], ref_at=(x2 + 2, yB + 3.8), val_at=(x2 + 2, yB + 6.3))
    r = sh.part("Device:R", "680", x2, yB + 13.97, 0, footprint=FP["R"], ref_at=(x2 + 2, yB + 12.7), val_at=(x2 + 2, yB + 15.2))
    sh.junction((x2, yB))
    sh.power(r.pin(2), "GND")
    # terminal A B GND
    j = sh.part("Connector:Screw_Terminal_01x03", f"RS485-{ch} A B GND", ox + 73.66, oy - 5.08, 0, footprint=FP["term03"], ref_at=(ox + 76, oy - 9), val_at=(ox + 76, oy - 1))
    sh.poly(j.pin(3), (ox + 66.04, oy - 2.54), (ox + 66.04, oy + 2.54))
    sh.power((ox + 66.04, oy + 2.54), "GND")


def serial_sheet(su):
    sh = Sheet("serial.kicad_sch", "Serial: two RS-485 channels (UART1, UART2) and a TTL header for UART5",
               sheet_uuid=su, path=f"/{ROOT_UUID}/{su}")
    sh.text((20, 20), "UART1 = P9.24/26 + DE P9.17, UART2 = P9.21/22 + DE P9.18 (profile example-modbus-rtu), UART5 = P8.37/38. DE high = drive; tied to ~RE so the receiver is muted while sending.", 1.5, True)
    rs485_block(sh, 30, 75, 0, 1)
    rs485_block(sh, 30, 170, 1, 2)
    # UART5 TTL header + loopback
    ox, oy = 220, 75
    sh.text((ox - 5, oy - 12), "UART5 TTL header (GND, 3V3, TXD, RXD) with loopback jumper J_LOOP", 1.27, True)
    j = sh.part("Connector:Conn_01x04_Pin", "UART5", ox + 10.16, oy, 0, footprint=FP["pin1x04"], ref_at=(ox + 9, oy - 6), val_at=(ox + 9, oy + 9))
    g = sh.poly(j.pin(1), (ox + 22.86, oy - 2.54), (ox + 22.86, oy - 7.62))
    sh.power(g, "GND", 180)
    sh.stub_power(j.pin(2), 12.7, 0, "+3V3")
    sh.wire(j.pin(3), (ox + 38.1, oy + 2.54)); sh.label((ox + 30.48, oy + 2.54), "UART5_TXD", 180)
    sh.wire(j.pin(4), (ox + 38.1, oy + 5.08)); sh.label((ox + 30.48, oy + 5.08), "UART5_RXD", 180)
    lp = sh.part("Connector:Conn_01x02_Pin", "J_LOOP", ox + 43.18, oy + 5.08, 180, footprint=FP["pin1x02"], ref_at=(ox + 44.5, oy + 1.5), val_at=(ox + 44.5, oy + 8))
    return sh


def i2c_pwm_sheet(su):
    sh = Sheet("i2c_pwm.kicad_sch", "I2C2 (Qwiic, expander, temperature), PWM / fan, button, debug header",
               sheet_uuid=su, path=f"/{ROOT_UUID}/{su}")
    sh.text((20, 20), "I2C2 = P9.19/20. Pull-ups 4.7k on solder jumpers (open them when the external device has its own). PWM0B = P9.29 (ehrpwm0B), FAN_TACH = P9.30, BTN = P9.23.", 1.5, True)
    ox, oy = 40, 60
    sh.text((ox - 10, oy - 22), "I2C pull-ups", 1.27, True)
    for i, net in enumerate(("I2C2_SCL", "I2C2_SDA")):
        x = ox + i * 15.24
        r = sh.part("Device:R", "4.7k", x, oy, 0, footprint=FP["R"], ref_at=(x + 2, oy - 1.2), val_at=(x + 2, oy + 1.3))
        sj = sh.part("Jumper:SolderJumper_2_Bridged", "SJ", x, oy - 8.89, 90, footprint=FP["sj"], ref_at=(x + 2, oy - 10), val_at=(x + 2, oy - 7.5), hide_val=True)
        top = sj.pin(1) if sj.pin(1)[1] < sj.pin(2)[1] else sj.pin(2)
        sh.power(top, "+3V3")
        sh.stub_label(r.pin(2), 0, net, dy=5.08)
    # PCF8574 expander
    X, Y = 110, 80
    sh.text((X - 25, Y - 30), "PCF8574 (addr 0x20): 8 extra I/O on a header, driver gpio-pcf857x", 1.27, True)
    u = sh.part("Interface_Expansion:PCF8574T", "PCF8574T", X, Y, 0, ref_at=(X - 8, Y - 20), val_at=(X + 2, Y - 20))
    sh.stub_label(u.pin(14), -5.08, "I2C2_SCL")
    sh.stub_label(u.pin(15), -5.08, "I2C2_SDA")
    sh.nc(u.pin(13))
    for p in (1, 2, 3):
        sh.wire(u.pin(p), (X - 15.24, u.pin(p)[1]))
    sh.wire((X - 15.24, u.pin(1)[1]), (X - 15.24, u.pin(3)[1] + 2.54))
    sh.junction((X - 15.24, u.pin(2)[1])); sh.junction((X - 15.24, u.pin(3)[1]))
    sh.power((X - 15.24, u.pin(3)[1] + 2.54), "GND")
    vcc = (X, u.pin(16)[1] - 2.54)
    sh.wire(u.pin(16), vcc); sh.power(vcc, "+3V3"); sh.junction(vcc)
    c = sh.part("Device:C", "100n", X + 7.62, vcc[1] + 3.81, 0, footprint=FP["C"], ref_at=(X + 9.5, vcc[1] + 2.5), val_at=(X + 9.5, vcc[1] + 5))
    sh.wire(vcc, c.pin(1)); sh.power(c.pin(2), "GND")
    sh.power(u.pin(8), "GND")
    for i, p in enumerate((4, 5, 6, 7, 9, 10, 11, 12)):
        sh.stub_label(u.pin(p), 5.08, f"EXP{i}")
    j = sh.part("Connector:Conn_01x10_Pin", "EXP", X + 50.8, Y, 0, footprint=FP["pin1x10"], ref_at=(X + 49.5, Y - 14), val_at=(X + 49.5, Y + 14))
    sh.stub_power(j.pin(1), 5.08, 0, "GND", 180)
    sh.stub_power(j.pin(2), 10.16, 0, "+3V3")
    for i in range(8):
        sh.stub_label(j.pin(3 + i), 5.08, f"EXP{i}")
    # TMP1075 temperature sensor
    X, Y = 110, 150
    sh.text((X - 25, Y - 18), "TMP1075 (addr 0x48), driver tmp102 / hwmon", 1.27, True)
    t = sh.part("Sensor_Temperature:TMP1075DGK", "TMP1075DGK", X, Y, 0, ref_at=(X - 8, Y - 12), val_at=(X + 2, Y - 12))
    sh.stub_label(t.pin(1), 5.08, "I2C2_SDA")
    sh.stub_label(t.pin(2), 5.08, "I2C2_SCL")
    sh.nc(t.pin(3))
    for p in (7, 6, 5):
        sh.wire(t.pin(p), (X - 15.24, t.pin(p)[1]))
    # address pins joined to GND; the decoupling cap sits above the join (pin2 on the A0 row)
    sh.wire((X - 15.24, t.pin(7)[1]), (X - 15.24, t.pin(5)[1] + 2.54))
    sh.junction((X - 15.24, t.pin(7)[1])); sh.junction((X - 15.24, t.pin(6)[1])); sh.junction((X - 15.24, t.pin(5)[1]))
    sh.power((X - 15.24, t.pin(5)[1] + 2.54), "GND")
    vcc = (X, t.pin(8)[1] - 2.54)
    sh.wire(t.pin(8), vcc); sh.power(vcc, "+3V3"); sh.junction(vcc)
    sh.wire(vcc, (X - 15.24, vcc[1]))
    c = sh.part("Device:C", "100n", X - 15.24, vcc[1] + 3.81, 0, footprint=FP["C"], ref_at=(X - 13.5, vcc[1] + 2.5), val_at=(X - 13.5, vcc[1] + 5))
    assert key(c.pin(1)) == key((X - 15.24, vcc[1])) and key(c.pin(2)) == key((X - 15.24, t.pin(7)[1]))
    sh.power(t.pin(4), "GND")
    # Qwiic + I2C pin header
    for k, (yy, lib_fp, name) in enumerate(((60, FP["qwiic"], "QWIIC"), (90, FP["pin1x04"], "I2C"))):
        X, Y = 230, yy
        sh.text((X - 5, Y - 8), f"{name}: GND, 3V3, SDA, SCL", 1.27, True)
        j = sh.part("Connector:Conn_01x04_Pin", name, X, Y, 0, footprint=lib_fp, ref_at=(X - 1.27, Y - 6), val_at=(X - 1.27, Y + 9))
        g = sh.poly(j.pin(1), (X + 10.16, Y - 2.54), (X + 10.16, Y - 7.62))
        sh.power(g, "GND", 180)
        sh.stub_power(j.pin(2), 10.16, 0, "+3V3")
        sh.stub_label(j.pin(3), 15.24, "I2C2_SDA")
        sh.stub_label(j.pin(4), 15.24, "I2C2_SCL")
    # PWM: LED, RC filter test point, fan header
    X, Y = 230, 130
    sh.text((X - 5, Y - 10), "PWM0B: LED, RC-filtered test point (10k/100n), 4-pin fan header (5 V fan, tach on FAN_TACH)", 1.27, True)
    sh.label((X, Y), "PWM0B", 180)
    sh.poly((X, Y), (X + 30.48, Y), (X + 30.48, Y + 7.62))
    r = sh.part("Device:R", "470", X + 7.62, Y + 3.81, 0, footprint=FP["R"], ref_at=(X + 9.5, Y + 2.5), val_at=(X + 9.5, Y + 5))
    sh.junction((X + 7.62, Y))
    led = sh.part("Device:LED", "PWM", X + 7.62, Y + 11.43, 90, footprint=FP["LED"], ref_at=(X + 9.5, Y + 10), val_at=(X + 9.5, Y + 12.5))
    sh.power(led.pin(1), "GND")
    rf = sh.part("Device:R", "10k", X + 17.78, Y + 3.81, 0, footprint=FP["R"], ref_at=(X + 19.5, Y + 2.5), val_at=(X + 19.5, Y + 5))
    sh.junction((X + 17.78, Y))
    node = rf.pin(2)
    sh.wire(node, (X + 17.78, Y + 10.16))
    cf = sh.part("Device:C", "100n", X + 17.78, Y + 13.97, 0, footprint=FP["C"], ref_at=(X + 19.5, Y + 12.7), val_at=(X + 19.5, Y + 15.2))
    sh.power(cf.pin(2), "GND")
    tp = sh.part("Connector:TestPoint", "PWM_FILT", X + 22.86, node[1], 0, footprint=FP["tp"], ref_at=(X + 21, node[1] - 5), val_at=(X + 21, node[1] - 2.5), hide_val=True)
    sh.wire(node, tp.pin(1)); sh.junction(node)
    fan = sh.part("Connector:Conn_01x04_Pin", "FAN", X + 40.64, Y + 2.54, 0, footprint=FP["pin1x04"], ref_at=(X + 39.5, Y - 4), val_at=(X + 39.5, Y + 11))
    sh.wire((X + 30.48, Y + 7.62), fan.pin(4))
    g = sh.poly(fan.pin(1), (X + 50.8, Y), (X + 50.8, Y - 5.08))
    sh.power(g, "GND", 180)
    sh.stub_power(fan.pin(2), 10.16, 0, "+5V")
    sh.wire(fan.pin(3), (X + 71.12, Y + 5.08)); sh.label((X + 71.12, Y + 5.08), "FAN_TACH", 0)
    rt = sh.part("Device:R", "10k", X + 66.04, Y + 1.27, 0, footprint=FP["R"], ref_at=(X + 68, Y), val_at=(X + 68, Y + 2.5))
    sh.junction((X + 66.04, Y + 5.08))
    sh.power(rt.pin(1), "+3V3")
    # button
    X, Y = 230, 175
    sh.text((X - 5, Y - 10), "BTN (P9.23, gpio1_17): button with 10k pull-up and 100n debounce", 1.27, True)
    sh.label((X, Y), "BTN", 180)
    sw = sh.part("Switch:SW_Push", "BTN", X + 25.4, Y, 0, footprint=FP["push"], ref_at=(X + 23, Y - 4), val_at=(X + 23, Y - 1.5), hide_val=True)
    sh.wire((X, Y), sw.pin(1))
    sh.stub_power(sw.pin(2), 2.54, 0, "GND")
    rp = sh.part("Device:R", "10k", X + 7.62, Y - 3.81, 0, footprint=FP["R"], ref_at=(X + 9.5, Y - 5), val_at=(X + 9.5, Y - 2.5))
    sh.junction((X + 7.62, Y)); sh.power(rp.pin(1), "+3V3")
    cd = sh.part("Device:C", "100n", X + 15.24, Y + 3.81, 0, footprint=FP["C"], ref_at=(X + 17, Y + 2.5), val_at=(X + 17, Y + 5))
    sh.junction((X + 15.24, Y)); sh.power(cd.pin(2), "GND")
    # debug header
    X, Y = 330, 80
    sh.text((X - 20, Y - 16), "Logic analyzer header: odd = Q0..Q7, even = I0..I7, 17/18 = GND", 1.27, True)
    j = sh.part("Connector_Generic:Conn_02x09_Odd_Even", "DEBUG", X, Y, 0, footprint=FP["pin2x09"], ref_at=(X - 1.27, Y - 14), val_at=(X - 1.27, Y + 14))
    for n in range(8):
        sh.stub_label(j.pin(1 + 2 * n), -7.62, f"Q{n}")
        sh.stub_label(j.pin(2 + 2 * n), 7.62, f"I{n}")
    sh.stub_power(j.pin(17), -7.62, 2.54, "GND")
    sh.stub_power(j.pin(18), 7.62, 2.54, "GND")
    return sh


def write_project():
    pro = {
        "board": {"design_settings": {"defaults": {}, "rules": {}}, "layer_presets": [], "viewports": []},
        "boards": [], "cvpcb": {"equivalence_files": []}, "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6,
                                      "via_drill": 0.3, "wire_width": 6, "bus_width": 12, "line_style": 0,
                                      "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
                                      "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
                                      "microvia_diameter": 0.3, "microvia_drill": 0.1}], "meta": {"version": 4}},
        "pcbnew": {"page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": [], "meta": {"version": 1}},
        "sheets": [[ROOT_UUID, "Root"]] + [[su, name] for name, _, su in SUBSHEETS],
        "text_variables": {},
    }
    with open(os.path.join(HERE, f"{PROJECT}.kicad_pro"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pro, fh, indent=2)


def main():
    root = root_sheet()
    outputs_sheet(SUBSHEETS[0][2])
    inputs_sheet(SUBSHEETS[1][2])
    analog_sheet(SUBSHEETS[2][2])
    serial_sheet(SUBSHEETS[3][2])
    i2c_pwm_sheet(SUBSHEETS[4][2])
    for sh in Sheet.all_sheets:
        sh.write(root=(sh is root))
    write_project()
    nets = Net.resolve()
    with open(os.path.join(HERE, "expected-nets.json"), "w", encoding="utf-8") as fh:
        json.dump(sorted(nets), fh, indent=1)
    n_parts = sum(v for k, v in Sheet.counters.items() if not k.startswith("#"))
    print(f"wrote {len(Sheet.all_sheets)} sheets, {n_parts} parts, {len(nets)} nets -> expected-nets.json")


if __name__ == "__main__":
    main()
