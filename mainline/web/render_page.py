#!/usr/bin/env python3
"""Render one UI page on the host to a self-contained HTML file (CSS inlined) for a visual check.

    python3 render_page.py /pinmux/breakout out.html
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("ANTMINER_PAYLOAD", os.path.join(HERE, "..", "out", "sdcard"))
from antminer_web import board  # noqa: E402
from antminer_web.server import create_app  # noqa: E402

board.PINMUX_DIR = os.path.join(HERE, "..", "pinmux")
app = create_app()
app.testing = True
html = app.test_client().get(sys.argv[1]).data.decode()
with open(os.path.join(HERE, "antminer_web", "static", "style.css")) as fh:
    css = fh.read()
html = re.sub(r'<link rel="stylesheet"[^>]*>', f"<style>{css}</style>", html)
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    fh.write(html)
print(f"wrote {sys.argv[2]} ({len(html)} bytes)")
