#!/usr/bin/env python3
"""Input-to-output latency from a logic analyzer CSV export (KingstVIS, PulseView/sigrok, Saleae).

Setup (see docs/10-latency.md): a hardware PWM output of the board drives an input pin (I0) and
LA channel A; the software under test copies I0 to Q0, which goes to LA channel B. Every edge on A
should be followed by one edge on B; the delay between them is the latency of that cycle.

    python latency.py capture.csv                        # channels 0 (stimulus) and 1 (response)
    python latency.py capture.csv --stim 2 --resp 5 --edge rising
    python latency.py capture.csv --rate 100e6           # export without a time column: sample index / rate
    python latency.py --selftest

CSV formats handled: a header row naming the columns, optional comment lines starting with ';' or
'#', first column = time (s, ms, us or ns, taken from the header) or a sample number; then one
column per channel with 0/1. Rows are only the samples where something changed (KingstVIS,
PulseView) or every sample: both work.
"""
import argparse
import csv
import math
import random
import re
import statistics
import sys

UNIT = {"s": 1.0, "sec": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}


def read_csv(path, rate):
    """-> (times in seconds, list of channel columns as lists of 0/1)"""
    times, cols, scale, header = [], None, None, None
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if not row or row[0].lstrip().startswith((";", "#")):
                continue
            cell = row[0].strip()
            if header is None and not re.match(r"^-?[\d.]+(e[-+]?\d+)?$", cell, re.I):
                header = [c.strip().lower() for c in row]
                m = re.search(r"[\[(]\s*(s|sec|ms|us|µs|ns)\s*[\])]|\b(ms|us|µs|ns)\b", header[0])
                unit = (m.group(1) or m.group(2)) if m else "s"
                scale = UNIT.get(unit, 1.0)
                continue
            vals = [c.strip() for c in row]
            if cols is None:
                cols = [[] for _ in vals[1:]]
            t = float(vals[0])
            times.append(t / rate if rate else t * (scale or 1.0))
            for i, v in enumerate(vals[1:]):
                cols[i].append(1 if v in ("1", "1.0", "true", "high") else 0)
    if not times:
        sys.exit("no samples in the file")
    return times, cols


def edges(times, col, kind):
    """timestamps of the chosen edges of one channel"""
    out = []
    for i in range(1, len(col)):
        if col[i] == col[i - 1]:
            continue
        rising = col[i] == 1
        if kind == "both" or (kind == "rising") == rising:
            out.append(times[i])
    return out


def pair(stim, resp, max_delay):
    """for every stimulus edge the first response edge after it (before the next stimulus edge)"""
    lat, missed, j = [], 0, 0
    for k, t in enumerate(stim):
        limit = stim[k + 1] if k + 1 < len(stim) else math.inf
        while j < len(resp) and resp[j] <= t:
            j += 1
        if j < len(resp) and resp[j] < limit and resp[j] - t <= max_delay:
            lat.append(resp[j] - t)
        else:
            missed += 1
    return lat, missed


def fmt(s):
    for unit, k in (("s", 1), ("ms", 1e-3), ("us", 1e-6), ("ns", 1e-9)):
        if abs(s) >= k or unit == "ns":
            return f"{s / k:8.2f} {unit}"


def report(lat, missed, n_stim, bins=20):
    if not lat:
        sys.exit(f"no stimulus/response pairs found ({n_stim} stimulus edges)")
    lat_sorted = sorted(lat)
    p = lambda q: lat_sorted[min(len(lat_sorted) - 1, int(q * len(lat_sorted)))]
    print(f"pairs      {len(lat)}   (stimulus edges {n_stim}, unanswered {missed})")
    print(f"min        {fmt(lat_sorted[0])}")
    print(f"median     {fmt(p(0.5))}")
    print(f"mean       {fmt(statistics.fmean(lat))}")
    print(f"p99        {fmt(p(0.99))}")
    print(f"p99.9      {fmt(p(0.999))}")
    print(f"max        {fmt(lat_sorted[-1])}")
    print(f"jitter     {fmt(lat_sorted[-1] - lat_sorted[0])}   (max - min)")
    if len(lat) > 1:
        print(f"stdev      {fmt(statistics.stdev(lat))}")
    lo, hi = lat_sorted[0], lat_sorted[-1]
    if hi > lo:
        width = (hi - lo) / bins
        counts = [0] * bins
        for v in lat:
            counts[min(bins - 1, int((v - lo) / width))] += 1
        top = max(counts)
        print("\nhistogram")
        for i, c in enumerate(counts):
            print(f"{fmt(lo + i * width)}  {'#' * int(40 * c / top):40s} {c}")


def selftest():
    random.seed(1)
    t, a, b = [], [], []
    now, state = 0.0, 0
    for _ in range(500):
        state ^= 1
        t.append(now); a.append(state); b.append(1 - state)             # stimulus edge
        d = 20e-6 + random.expovariate(1 / 5e-6)
        t.append(now + d); a.append(state); b.append(state)             # response edge
        now += 5e-3
    lat, missed = pair(edges(t, a, "both"), edges(t, b, "both"), 1.0)
    report(lat, missed, 500)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--stim", type=int, default=0, help="channel column of the stimulus (0 = first after time)")
    ap.add_argument("--resp", type=int, default=1, help="channel column of the response")
    ap.add_argument("--edge", choices=("rising", "falling", "both"), default="both")
    ap.add_argument("--rate", type=float, help="sample rate in Hz when the first column is a sample number")
    ap.add_argument("--max-delay", type=float, default=1.0, help="ignore responses later than this (s)")
    ap.add_argument("--out", help="write the per-cycle latencies (s) to this file")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.csv:
        ap.error("csv file required")
    times, cols = read_csv(a.csv, a.rate)
    if max(a.stim, a.resp) >= len(cols):
        sys.exit(f"the file has {len(cols)} channel columns")
    stim = edges(times, cols[a.stim], a.edge)
    resp = edges(times, cols[a.resp], a.edge)
    lat, missed = pair(stim, resp, a.max_delay)
    print(f"capture    {fmt(times[-1] - times[0])}, {len(times)} rows")
    report(lat, missed, len(stim))
    if a.out:
        with open(a.out, "w") as fh:
            fh.write("\n".join(repr(v) for v in lat) + "\n")


if __name__ == "__main__":
    main()
