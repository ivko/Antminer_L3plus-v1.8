#!/usr/bin/env python3
"""Render every page of the web UI on the development host (no board needed).

    python3 test_smoke.py            # uses repo/mainline/pinmux and out/sdcard as stand-ins
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("ANTMINER_PAYLOAD", os.path.join(HERE, "..", "out", "sdcard"))

from antminer_web import board  # noqa: E402
from antminer_web.server import create_app  # noqa: E402

board.PINMUX_DIR = os.path.join(HERE, "..", "pinmux")      # gen-dts.py + pad db live here on the host
# shipped profiles are in pinmux/boards, local ones would be in /config/pinmux (absent here)

app = create_app()
app.testing = True
c = app.test_client()
failed = 0
for path in ("/", "/api/status", "/nand", "/pinmux", "/pinmux/pads", "/pinmux/breakout", "/pinmux/breakout/board",
             "/api/pads", "/api/profiles", "/api/profiles/breakout", "/services", "/log"):
    r = c.get(path)
    ok = r.status_code == 200
    failed += not ok
    print(f"{'ok ' if ok else 'ERR'} {r.status_code} {path} ({len(r.data)} bytes)")
    if not ok:
        print(r.data.decode(errors="replace")[:800])

# profile model round trip for every shipped profile
from antminer_web import profile  # noqa: E402
import glob  # noqa: E402
for y in sorted(glob.glob(os.path.join(board.PINMUX_DIR, "boards", "*.yaml"))):
    with open(y) as fh:
        text = fh.read()
    ok = profile.roundtrip_ok(text)
    failed += not ok
    m = profile.load(text)
    print(f"{'ok ' if ok else 'ERR'} roundtrip {os.path.basename(y)}: {len(m['pins'])} pins, adc {m['adc']}")
# YAML produced by the editor must be accepted back by the generator-side loader
r = c.post("/api/profiles/breakout/yaml", json=profile.load(open(os.path.join(board.PINMUX_DIR, "boards", "breakout.yaml")).read()))
print(f"{'ok ' if r.status_code == 200 else 'ERR'} {r.status_code} /api/profiles/breakout/yaml ({len(r.data)} bytes)")
failed += r.status_code != 200
sys.exit(1 if failed else 0)
