#!/usr/bin/env python3
"""UDP flood for the latency load tests: ~3000 small packets/s to the board (docs/10-latency.md).

    python latency-flood.py 192.168.200.107            # until Ctrl-C
    python latency-flood.py 192.168.200.107 --pps 5000 --seconds 120
"""
import argparse, socket, time
ap = argparse.ArgumentParser()
ap.add_argument("host"); ap.add_argument("--port", type=int, default=9)
ap.add_argument("--pps", type=int, default=3000); ap.add_argument("--seconds", type=float, default=0)
a = ap.parse_args()
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
payload = b"x" * 64
end = time.time() + a.seconds if a.seconds else None
sent, t0 = 0, time.time()
try:
    while end is None or time.time() < end:
        s.sendto(payload, (a.host, a.port)); sent += 1
        target = t0 + sent / a.pps
        d = target - time.time()
        if d > 0:
            time.sleep(d)
except KeyboardInterrupt:
    pass
print(f"sent {sent} packets in {time.time() - t0:.1f} s")
