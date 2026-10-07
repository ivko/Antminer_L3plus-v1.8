#!/usr/bin/env python3
"""Generate the per-board device tree source for the Antminer BB-Black V1.8 I/O module.

    python3 gen-dts.py boards/default.yaml -o ../dts/am335x-antminer.dts

Input: a YAML profile (see boards/*.yaml). Output: a .dts that includes
am335x-antminer-base.dtsi (fixed hardware) and adds, for every pad listed:
  - the pinmux entry (mode + pull + receiver) in a pinctrl group per peripheral,
  - the peripheral node enable (&uartN, &i2cN, &spiN, &ehrpwmN/&ecapN, &dcanN, &eqepN),
  - for GPIOs: gpio-line-names, optional gpio-hog, pull resistor = safe level before userspace,
  - ADC channels for &tscadc.
Pads are addressed by BeagleBone header name ("P8.43"), by pad name ("lcd_data2") or by GPIO
name ("gpio2_8"). Pads the fixed part owns (NAND, Ethernet, console UART0, I2C0 PMIC, SD card
detect, user LEDs) are refused with the reason.

Profile format:
  name: default                      # free text, goes into the DT model string
  pins:
    P9.24: uart1_txd                 # shorthand: just the function
    P9.26: {func: uart1_rxd, pull: up}
    P8.43: {func: gpio, dir: out, init: 0, name: Q0}      # pull follows init (0->down, 1->up)
    P8.45: {func: gpio, dir: in,  pull: up, name: I0, hog: false}
    uart0_ctsn: uart4_rxd            # pad name, for pads that are not on P8/P9
  adc: [0, 1, 2, 3, 4, 5, 6, 7]      # AIN channels to enable (1.8 V inputs)
  i2c:  {i2c2: {clock-frequency: 100000}}         # optional per-peripheral extras
  i2c:  {i2c2: {devices: [{compatible: "nxp,pcf8574", reg: 0x20, props: {...}}]}}  # child nodes
  spi:  {spi0: {spidev: [0], max-frequency: 16000000}}
  unused: default                    # default: every other free pad -> GPIO input pull-down; keep: leave alone
Options per pin: func, pull (up|down|none), rx (true|false), slew (fast|slow),
dir (in|out, gpio only), init (0|1, gpio out), name (gpio line name), hog (true|false).
"""
import argparse
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML missing: apt-get install python3-yaml")

HERE = os.path.dirname(os.path.abspath(__file__))

# pad conf register bits (dt-bindings/pinctrl/am33xx.h)
PULL_DISABLE = 1 << 3
PULL_UP = 1 << 4
INPUT_EN = 1 << 5
SLEW_SLOW = 1 << 6

# Pads that are not on the BeagleBone P8/P9 headers but are wired on the Bitmain board
# (hash board connectors). Modes from the AM335x TRM / datasheet.
EXTRA_PADS = {
    "uart0_ctsn": {"offset": 0x968, "gpio": [1, 8],
                   "modes": ["uart0_ctsn", "uart4_rxd", "dcan1_tx", "i2c1_sda", "spi1_d0", "timer7", "pr1_edc_sync0_out", "gpio1[8]"]},
    "uart0_rtsn": {"offset": 0x96c, "gpio": [1, 9],
                   "modes": ["uart0_rtsn", "uart4_txd", "dcan1_rx", "i2c1_scl", "spi1_d1", "spi1_cs0", "pr1_edc_sync1_out", "gpio1[9]"]},
    "gpmc_a4": {"offset": 0x850, "gpio": [1, 20],
                "modes": ["gpmc_a4", "gmii2_txd1", "rgmii2_td1", "rmii2_txd1", "gpmc_a20", "pr1_mii1_txd0", "eqep1a_in", "gpio1[20]"]},
    "mcasp0_aclkr": {"offset": 0x9a0, "gpio": [3, 18],
                     "modes": ["mcasp0_aclkr", "eqep0a_in", "mcasp0_axr2", "mcasp1_aclkx", "mmc0_sdwp", "pr1_pru0_pru_r30_4", "pr1_pru0_pru_r31_4", "gpio3[18]"]},
    "mcasp0_axr1": {"offset": 0x9a8, "gpio": [3, 20],
                    "modes": ["mcasp0_axr1", "eqep0_index", "mcasp0_axr2", "mcasp1_axr0", "emu3", "pr1_pru0_pru_r30_6", "pr1_pru0_pru_r31_6", "gpio3[20]"]},
    "xdma_event_intr0": {"offset": 0x9b0, "gpio": [0, 19],
                         "modes": ["xdma_event_intr0", None, "timer4", "clkout1", "spi1_cs1", "pr1_pru1_pru_r31_16", "emu2", "gpio0[19]"]},
    # mii1_col / mii1_crs are not used by the MII PHY connection (am335x-bone-common cpsw_default
    # starts at mii1_rx_er), so they are free GPIOs here
    "mii1_col": {"offset": 0x908, "gpio": [3, 0],
                 "modes": ["mii1_col", "rmii2_refclk", "spi1_sclk", "uart5_rxd", "mcasp1_axr2", "mmc2_dat3", "mcasp0_axr2", "gpio3[0]"]},
    "mii1_crs": {"offset": 0x90c, "gpio": [3, 1],
                 "modes": ["mii1_crs", "rmii1_crs_dv", "spi1_d0", "i2c1_sda", "mcasp1_aclkx", "uart5_ctsn", "uart2_rxd", "gpio3[1]"]},
}

# Pads owned by am335x-antminer-base.dtsi (+ am335x-bone-common.dtsi parts we keep)
RESERVED = {}
for off in list(range(0x800, 0x820, 4)) + [0x870, 0x874, 0x87c, 0x890, 0x894, 0x898, 0x89c]:
    RESERVED[off] = "NAND (GPMC)"
for off in range(0x910, 0x944, 4):   # mii1_rx_er .. mii1_rxd0 (am335x-bone-common cpsw_default)
    RESERVED[off] = "Ethernet MII"
RESERVED[0x948] = RESERVED[0x94c] = "Ethernet MDIO"
RESERVED[0x970] = RESERVED[0x974] = "console UART0"
RESERVED[0x988] = RESERVED[0x98c] = "I2C0 (TPS65217 PMIC)"
for off in range(0x8f0, 0x908, 4):
    RESERVED[off] = "microSD (mmc0)"
RESERVED[0x960] = "microSD card detect"
for off in range(0x854, 0x864, 4):
    RESERVED[off] = "user LEDs usr0..3"

# function class -> default pad configuration
def default_conf(func):
    f = func.lower()
    if f == "gpio":
        return INPUT_EN  # pull decided from dir/init
    if re.match(r"uart\d_(rxd|ctsn)$", f) or re.match(r"dcan\d_rx$", f):
        return INPUT_EN | PULL_UP
    if re.match(r"uart\d_(txd|rtsn)$", f):
        return 0  # output, pulldown
    if re.match(r"dcan\d_tx$", f):
        return PULL_UP
    if re.match(r"i2c\d_(sda|scl)$", f):
        return INPUT_EN | PULL_UP
    if re.match(r"spi\d_(sclk|d0|d1)$", f):
        return INPUT_EN | PULL_UP
    if re.match(r"spi\d_cs\d$", f):
        return PULL_UP
    if re.match(r"(ehrpwm\d[ab]|ecap\d_in_pwm\d_out|timer\d)$", f):
        return 0
    if re.match(r"eqep\d", f):
        return INPUT_EN | PULL_UP
    return INPUT_EN | PULL_DISABLE


def periph_of(func):
    """Return (node_label, group_key) for a peripheral function, or None for GPIO/other."""
    f = func.lower()
    m = re.match(r"uart(\d)_", f)
    if m: return (f"uart{m.group(1)}", f"uart{m.group(1)}")
    m = re.match(r"i2c(\d)_", f)
    if m: return (f"i2c{m.group(1)}", f"i2c{m.group(1)}")
    m = re.match(r"spi(\d)_", f)
    if m: return (f"spi{m.group(1)}", f"spi{m.group(1)}")
    m = re.match(r"ehrpwm(\d)[ab]$", f)
    if m: return (f"ehrpwm{m.group(1)}", f"ehrpwm{m.group(1)}")
    m = re.match(r"ecap(\d)_in_pwm\d_out$", f)
    if m: return (f"ecap{m.group(1)}", f"ecap{m.group(1)}")
    m = re.match(r"dcan(\d)_", f)
    if m: return (f"dcan{m.group(1)}", f"dcan{m.group(1)}")
    m = re.match(r"eqep(\d)", f)
    if m: return (f"eqep{m.group(1)}", f"eqep{m.group(1)}")
    m = re.match(r"timer(\d)$", f)
    if m: return (None, f"timer{m.group(1)}")  # mux only, no node to enable
    return None


FORBIDDEN_FUNC = re.compile(r"^(pr1_|mcasp|mmc|gpmc|g?mii|rg?mii|mdio|lcd_|emu|clkout|tclkin|xdma)")


class Gen:
    def __init__(self, pins_db):
        self.db = {}
        for key, v in pins_db.items():
            if v["offset"] is None:
                continue
            e = {"offset": v["offset"], "modes": [m.lower() if m else None for m in v["modes"]],
                 "gpio": v["gpio"], "header": key, "pad": (v["modes"][0] or "").lower()}
            self.db[key.upper()] = e
            self.db[e["pad"]] = e
            if e["gpio"]:
                self.db[f"gpio{e['gpio'][0]}_{e['gpio'][1]}"] = e
        for pad, v in EXTRA_PADS.items():
            e = {"offset": v["offset"], "modes": [m.lower() if m else None for m in v["modes"]],
                 "gpio": v["gpio"], "header": None, "pad": pad}
            self.db.setdefault(pad, e)
            self.db.setdefault(f"gpio{v['gpio'][0]}_{v['gpio'][1]}", e)
        self.errors, self.warnings = [], []
        self.groups = {}        # group key -> list of (offset, value, comment)
        self.periphs = {}       # node label -> group key
        self.gpio_names = {b: [""] * 32 for b in range(4)}
        self.hogs = {b: [] for b in range(4)}
        self.used = {}          # offset -> key
        self.pins_out = []      # structured per-pin result for --json (web UI)

    def lookup(self, key):
        k = key.strip()
        for cand in (k.upper(), k.lower(), k.upper().replace("_", ".")):
            if cand in self.db:
                return self.db[cand]
        return None

    def add_pin(self, key, spec):
        if isinstance(spec, str):
            spec = {"func": spec}
        e = self.lookup(key)
        if not e:
            self.errors.append(f"{key}: unknown pin/pad"); return
        off = e["offset"]
        if off in RESERVED:
            self.errors.append(f"{key} (0x{off:x}, {e['pad']}): reserved for {RESERVED[off]}"); return
        if off in self.used:
            self.errors.append(f"{key}: pad 0x{off:x} already used by {self.used[off]}"); return
        func = str(spec.get("func", "gpio")).lower()
        if FORBIDDEN_FUNC.match(func) and func != "gpio":
            self.errors.append(f"{key}: function {func} is not usable on this board"); return
        if func == "gpio":
            mode = 7
            if not e["gpio"]:
                self.errors.append(f"{key}: no GPIO on this pad"); return
        else:
            if func not in [m for m in e["modes"] if m]:
                avail = ", ".join(m for m in e["modes"] if m)
                self.errors.append(f"{key}: {func} not available; modes: {avail}"); return
            mode = e["modes"].index(func)
        self.used[off] = key

        conf = default_conf(func)
        if func == "gpio":
            d = str(spec.get("dir", "in")).lower()
            init = int(spec.get("init", 0))
            if "pull" in spec:
                conf = self.apply_pull(conf, spec["pull"])
            elif d == "out":
                conf |= PULL_UP if init else 0          # safe level before userspace drives it
            else:
                conf |= 0                                # input: pulldown unless asked
        elif "pull" in spec:
            conf = self.apply_pull(conf, spec["pull"])
        if "rx" in spec:
            conf = (conf | INPUT_EN) if spec["rx"] else (conf & ~INPUT_EN)
        if str(spec.get("slew", "fast")).lower() == "slow":
            conf |= SLEW_SLOW
        value = conf | mode

        label = f"{e['header'] or e['pad']}"
        info = {"key": key, "label": label, "pad": e["pad"], "offset": off, "value": value, "func": func,
                "gpio": f"gpio{e['gpio'][0]}_{e['gpio'][1]}" if e["gpio"] else None,
                "comment": spec.get("comment")}
        if func == "gpio":
            b, l = e["gpio"]
            name = str(spec.get("name", f"{label.replace('.', '_')}"))
            self.gpio_names[b][l] = name
            comment = f"{label} {e['pad']} gpio{b}_{l} {name} {spec.get('dir','in')}"
            self.groups.setdefault("board_gpio", []).append((off, value, comment))
            info.update(name=name, dir=str(spec.get("dir", "in")).lower(), line=b * 32 + l)
            if spec.get("hog"):
                d = str(spec.get("dir", "in")).lower()
                hog = "input" if d == "in" else ("output-high" if int(spec.get("init", 0)) else "output-low")
                self.hogs[b].append((l, name, hog))
                info["hog"] = hog
        else:
            p = periph_of(func)
            if p is None:
                self.errors.append(f"{key}: don't know which peripheral {func} belongs to"); return
            node, gkey = p
            self.groups.setdefault(gkey, []).append((off, value, f"{label} {e['pad']} -> {func}"))
            info.update(peripheral=node or gkey)
            if node:
                self.periphs[node] = gkey
        self.pins_out.append(info)

    def json_result(self):
        """machine-readable summary for the web UI: errors keep the 'pin: text' shape"""
        def split(msg):
            k, _, t = msg.partition(": ")
            return {"pin": k.split(" ")[0] if t else None, "text": t or msg}
        return {"ok": not self.errors, "errors": [split(e) for e in self.errors],
                "warnings": [split(w) for w in self.warnings], "pins": self.pins_out,
                "peripherals": sorted(self.periphs),
                "unused_pads": len(self.groups.get("unused_pads", []))}

    @staticmethod
    def apply_pull(conf, pull):
        conf &= ~(PULL_DISABLE | PULL_UP)
        p = str(pull).lower()
        if p == "up": return conf | PULL_UP
        if p == "down": return conf
        if p in ("none", "off", "disable"): return conf | PULL_DISABLE
        raise ValueError(f"bad pull '{pull}'")

    def add_unused(self, profile):
        """Every known free pad not listed in the profile gets the reset state explicitly
        (GPIO input, pull-down, 0x27). Without this a pad keeps whatever U-Boot or the previous
        boot left (warm reboot), i.e. behaviour would depend on history. unused: keep disables it."""
        policy = str(profile.get("unused", "default")).lower()
        if policy == "keep":
            return
        seen = set()
        for e in self.db.values():
            off = e["offset"]
            if off in seen or off in RESERVED or off in self.used:
                continue
            seen.add(off)
            if not e["gpio"]:
                continue
            value = INPUT_EN | 7  # input, pull-down (pull enabled, PULL_UP clear), mode 7
            label = e["header"] or e["pad"]
            self.groups.setdefault("unused_pads", []).append((off, value, f"{label} {e['pad']} unused -> gpio in pulldown"))

    def check(self, profile):
        for gkey, pins in self.groups.items():
            funcs = [c.split("-> ")[-1] for _, _, c in pins]
            if gkey.startswith("uart") and not ({f"{gkey}_rxd", f"{gkey}_txd"} <= set(funcs)):
                self.warnings.append(f"{gkey}: both rxd and txd are normally needed ({', '.join(funcs)})")
            if gkey.startswith("i2c") and not ({f"{gkey}_sda", f"{gkey}_scl"} <= set(funcs)):
                self.errors.append(f"{gkey}: needs both sda and scl ({', '.join(funcs)})")
            if gkey.startswith("spi") and f"{gkey}_sclk" not in funcs:
                self.errors.append(f"{gkey}: needs sclk ({', '.join(funcs)})")
            if gkey.startswith("dcan") and not ({f"{gkey}_rx", f"{gkey}_tx"} <= set(funcs)):
                self.errors.append(f"{gkey}: needs both rx and tx")
        for ch in profile.get("adc", []):
            if not (0 <= int(ch) <= 7):
                self.errors.append(f"adc channel {ch} out of range 0..7")

    def emit(self, profile, src_name, flat_base=None):
        """flat_base: name of a cpp-preprocessed base (am335x-antminer-base.pp.dtsi). Then the
        output needs only dtc, no cpp and no kernel tree: dtc '/include/' instead of '#include',
        numeric pinctrl cells instead of AM33XX_IOPAD(). That is how the board itself builds DTBs."""
        name = str(profile.get("name", "custom"))
        out = []
        w = out.append
        w("// SPDX-License-Identifier: GPL-2.0-only")
        w(f"/* GENERATED by pinmux/gen-dts.py from {src_name} - do not edit, edit the YAML. */")
        w("/dts-v1/;")
        w("")
        if flat_base:
            w(f'/include/ "{flat_base}"')
        else:
            w('#include "am335x-antminer-base.dtsi"')
        w("")

        def pad(off, val):
            # AM33XX_IOPAD(pa, val) = (pa - 0x800) (val) (0)  [dt-bindings/pinctrl/omap.h, 6.12]
            if flat_base:
                return f"0x{off - 0x800:03x} 0x{val:02x} 0x0"
            return f"AM33XX_IOPAD(0x{off:03x}, 0x{val:02x})"
        w("/ {")
        w(f'\tmodel = "Bitmain Antminer BB-Black V1.8 (AM3352), profile {name}";')
        w("};")
        w("")
        # pin map comment (unused pads are summarised, not listed)
        w("/*")
        w(" * Pin map:")
        for gkey, pins in self.groups.items():
            if gkey == "unused_pads":
                continue
            for off, val, c in sorted(pins):
                w(f" *   0x{off:03x} = 0x{val:02x}  {c}")
        if "unused_pads" in self.groups:
            w(f" *   + {len(self.groups['unused_pads'])} unused free pads forced to GPIO input pull-down (0x27)")
        w(" */")
        w("")
        # pinmux: the pinmux node itself hogs the GPIO groups (board + unused pads)
        w("&am33xx_pinmux {")
        hogs = [g for g in ("board_gpio", "unused_pads") if g in self.groups]
        if hogs:
            w("\tpinctrl-names = \"default\";")
            w("\tpinctrl-0 = <" + ">, <".join(f"&{g}_pins" for g in hogs) + ">;")
            w("")
        for gkey, pins in self.groups.items():
            lbl = f"{gkey}_pins"
            w(f"\t{lbl}: {lbl.replace('_', '-')} {{")
            w("\t\tpinctrl-single,pins = <")
            for off, val, c in sorted(pins):
                w(f"\t\t\t{pad(off, val)}\t/* {c} */")
            w("\t\t>;")
            w("\t};")
            w("")
        w("};")
        w("")
        # peripherals
        pwmss = set()
        for node, gkey in sorted(self.periphs.items()):
            extra = {}
            for sect in ("uart", "i2c", "spi", "pwm", "can"):
                extra.update((profile.get(sect) or {}).get(node, {}) or {})
            if node.startswith(("ehrpwm", "ecap")):
                pwmss.add(f"epwmss{node[-1]}")
            w(f"&{node} {{")
            w("\tstatus = \"okay\";")
            w("\tpinctrl-names = \"default\";")
            w(f"\tpinctrl-0 = <&{gkey}_pins>;")
            if node.startswith("i2c"):
                w(f"\tclock-frequency = <{int(extra.get('clock-frequency', 100000))}>;")
                # devices: [{compatible: "nxp,pcf8574", reg: 0x20, label: ext_io,
                #            props: {gpio-controller: true, "#gpio-cells": 2, gpio-line-names: [EXP0, ...]}}]
                devs = extra.get("devices") or []
                if devs:
                    w("\t#address-cells = <1>;")
                    w("\t#size-cells = <0>;")
                for dev in devs:
                    reg = int(dev["reg"])
                    label = dev.get("label")
                    node_name = dev.get("node", dev["compatible"].split(",")[-1])
                    w(f"\t{label + ': ' if label else ''}{node_name}@{reg:x} {{")
                    w(f"\t\tcompatible = \"{dev['compatible']}\";")
                    w(f"\t\treg = <0x{reg:x}>;")
                    for k, v in (dev.get("props") or {}).items():
                        if v is True:
                            w(f"\t\t{k};")
                        elif isinstance(v, bool):
                            continue
                        elif isinstance(v, int):
                            w(f"\t\t{k} = <{v}>;")
                        elif isinstance(v, list):
                            w(f"\t\t{k} = " + ", ".join(f"\"{x}\"" if isinstance(x, str) else f"<{int(x)}>" for x in v) + ";")
                        else:
                            w(f"\t\t{k} = \"{v}\";")
                    w("\t};")
            if node.startswith("spi"):
                w("\t#address-cells = <1>;")
                w("\t#size-cells = <0>;")
                for cs in extra.get("spidev", [0]):
                    w(f"\tspidev@{cs} {{")
                    w("\t\tcompatible = \"rohm,dh2228fv\";\t/* spidev needs a real-looking id */")
                    w(f"\t\treg = <{cs}>;")
                    w(f"\t\tspi-max-frequency = <{int(extra.get('max-frequency', 16000000))}>;")
                    w("\t};")
            w("};")
            w("")
        for m in sorted(pwmss):
            w(f"&{m} {{")
            w("\tstatus = \"okay\";")
            w("};")
            w("")
        # adc
        adc = profile.get("adc") or []
        if adc:
            w("&tscadc {")
            w("\tstatus = \"okay\";")
            w("\tadc {")
            w(f"\t\tti,adc-channels = <{' '.join(str(int(c)) for c in adc)}>;")
            w("\t};")
            w("};")
            w("")
        # gpio names + hogs
        for b in range(4):
            names = self.gpio_names[b]
            if not any(names) and not self.hogs[b]:
                continue
            w(f"&gpio{b} {{")
            if any(names):
                w("\tgpio-line-names =")
                for r in range(4):
                    row = ", ".join(f'"{n}"' for n in names[r * 8:(r + 1) * 8])
                    w(f"\t\t{row}{';' if r == 3 else ','}")
            for line, name, hog in self.hogs[b]:
                w(f"\t{name.lower()}-hog {{")
                w("\t\tgpio-hog;")
                w(f"\t\tgpios = <{line} 0>;")
                w(f"\t\t{hog};")
                w(f'\t\tline-name = "{name}";')
                w("\t};")
            w("};")
            w("")
        return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile")
    ap.add_argument("-o", "--output", help="output .dts (default: stdout)")
    ap.add_argument("--pins", default=os.path.join(HERE, "am335x-bbb-pins.json"))
    ap.add_argument("--flat", metavar="BASE_PP_DTSI",
                    help="emit a dtc-only .dts that /include/s this preprocessed base (no cpp needed)")
    ap.add_argument("--json", metavar="FILE", help="also write a JSON summary (pins, errors) for the web UI")
    a = ap.parse_args()
    with open(a.pins) as f:
        db = json.load(f)
    with open(a.profile) as f:
        profile = yaml.safe_load(f) or {}
    g = Gen(db)
    for key, spec in (profile.get("pins") or {}).items():
        try:
            g.add_pin(str(key), spec)
        except Exception as ex:  # noqa: BLE001
            g.errors.append(f"{key}: {ex}")
    g.check(profile)
    if not g.errors:
        g.add_unused(profile)
    for wmsg in g.warnings:
        print(f"warning: {wmsg}", file=sys.stderr)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(g.json_result(), f, indent=1)
    if g.errors:
        for e in g.errors:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    dts = g.emit(profile, os.path.basename(a.profile), flat_base=a.flat)
    if a.output:
        with open(a.output, "w", newline="\n") as f:
            f.write(dts)
        print(f"wrote {a.output}: {sum(len(v) for v in g.groups.values())} pads, "
              f"peripherals: {', '.join(sorted(g.periphs)) or 'none'}")
    else:
        sys.stdout.write(dts)


if __name__ == "__main__":
    main()
