#!/usr/bin/env python3
"""Extract the AM335x / BeagleBone P8+P9 pin table from repo/docs/BBB_Pins.xlsx into
pinmux/am335x-bbb-pins.json for gen-dts.py.

    python3 extract-pins.py            # reads ../docs/BBB_Pins.xlsx, writes am335x-bbb-pins.json

Each entry: header pin "P8.3" -> {"ball","name","offset" (0x800-based, int),
"modes": [8 names, None where unavailable], "gpio": [bank, line] from the mode-7 name}.
Power/ground pins and pins without a pad offset (ADC inputs) are kept with offset null.
"""
import json
import os
import re
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(HERE, "..", "..", "docs", "BBB_Pins.xlsx")
OUT = os.path.join(HERE, "am335x-bbb-pins.json")

wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
pins = {}
for sheet in ("P8", "P9"):
    ws = wb[sheet]
    for row in ws.iter_rows(min_row=3, values_only=True):
        if row[0] is None or not isinstance(row[0], (int, float)):
            continue
        pin = int(row[0])
        key = f"{sheet}.{pin}"
        name = str(row[2]).strip() if row[2] is not None else ""
        off = row[3]
        offset = None
        if isinstance(off, str) and off.strip().startswith("0x"):
            offset = int(off, 16) + 0x800
        elif isinstance(off, (int, float)):
            offset = int(off) + 0x800
        modes = []
        for m in row[4:12]:
            if m is None:
                modes.append(None)
            else:
                ms = str(m).strip()
                modes.append(None if ms in ("-", "", "None") else ms)
        gpio = None
        if modes and modes[7]:
            mm = re.match(r"gpio(\d)\[(\d+)\]", modes[7])
            if mm:
                gpio = [int(mm.group(1)), int(mm.group(2))]
        entry = {"ball": None if row[1] in (None, "-") else str(row[1]), "name": name,
                 "offset": offset, "modes": modes, "gpio": gpio}
        if key in pins:  # second pad on the same header pin (P9.41 / P9.42)
            pins[key + "b"] = entry
        else:
            pins[key] = entry

with open(OUT, "w") as f:
    json.dump(pins, f, indent=1)
print(f"{len(pins)} pins -> {OUT}")
with_pad = [k for k, v in pins.items() if v["offset"] is not None]
print(f"{len(with_pad)} with a pad offset, {len(pins) - len(with_pad)} power/ADC/other")
