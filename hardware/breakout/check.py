#!/usr/bin/env python3
"""Compare KiCad's netlist (kicad-cli sch export netlist --format kicadsexpr) with the
connectivity gen-sch.py intended (expected-nets.json). Any difference means a wire or pin
landed somewhere else than planned.

    python check.py [breakout.net]
"""
import json
import os
import sys

import kisym

HERE = os.path.dirname(os.path.abspath(__file__))


def kicad_nets(path):
    with open(path, encoding="utf-8") as fh:
        root = kisym.parse(fh.read())[0]
    nets = kisym.child(root, "nets")
    out = []
    for net in kisym.children(nets, "net"):
        name = kisym.unq(kisym.child(net, "name")[1])
        nodes = sorted(f"{kisym.unq(kisym.child(n, 'ref')[1])}.{kisym.unq(kisym.child(n, 'pin')[1])}"
                       for n in kisym.children(net, "node"))
        out.append((name, nodes))
    return out


def main():
    netfile = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "breakout.net")
    with open(os.path.join(HERE, "expected-nets.json"), encoding="utf-8") as fh:
        expected = [(n, sorted(p)) for n, p in json.load(fh)]
    actual = kicad_nets(netfile)
    exp_sets = {frozenset(p): n for n, p in expected if p}
    act_sets = {frozenset(p): n for n, p in actual if p}
    ok = True
    for s, n in act_sets.items():
        if s not in exp_sets:
            ok = False
            # find the expected groups that overlap this one
            overl = [(en, sorted(es & s), sorted(es - s)) for es, en in exp_sets.items() if es & s]
            print(f"KiCad net {n!r} {sorted(s)}")
            for en, common, missing in overl:
                print(f"   expected {en!r}: shares {common}, we also expected {missing}")
    for s, n in exp_sets.items():
        if s not in act_sets:
            ok = False
            print(f"expected net {n!r} {sorted(s)} not found as one KiCad net")
    print(f"{len(act_sets)} KiCad nets, {len(exp_sets)} expected: {'MATCH' if ok else 'MISMATCH'}")
    # power nets must carry the intended names
    for want in ("GND", "GNDA", "+3V3", "+5V", "VDD_ADC", "+24V"):
        names = [n for n, p in actual if n == want]
        if not names:
            print(f"warning: no KiCad net named {want}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
