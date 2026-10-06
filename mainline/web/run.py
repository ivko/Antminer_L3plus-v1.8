#!/usr/bin/env python3
"""Start the Antminer web UI (Flask).  python3 run.py [--port 80] [--debug]"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from antminer_web.server import create_app  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=80)
ap.add_argument("--host", default="0.0.0.0")
ap.add_argument("--debug", action="store_true")
a = ap.parse_args()
create_app().run(host=a.host, port=a.port, debug=a.debug, threaded=True)
