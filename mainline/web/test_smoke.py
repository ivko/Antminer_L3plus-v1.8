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
for path in ("/", "/api/status", "/nand", "/pinmux", "/pinmux/pads", "/pinmux/breakout", "/services", "/log"):
    r = c.get(path)
    ok = r.status_code == 200
    failed += not ok
    print(f"{'ok ' if ok else 'ERR'} {r.status_code} {path} ({len(r.data)} bytes)")
    if not ok:
        print(r.data.decode(errors="replace")[:800])
sys.exit(1 if failed else 0)
