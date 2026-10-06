#!/usr/bin/env python3
"""Minimal KiCad S-expression reader for .kicad_sym libraries.

    python kisym.py Device:R Transistor_FET:AO3400A      # dump pins of symbols

Used by gen-sch.py to embed library symbols (flattened, `extends` resolved) into the
generated schematic and to know where each pin's connection point is.
"""
import os
import re
import sys

KICAD_SHARE = os.environ.get("KICAD_SHARE") or os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "KiCad", "10.0", "share", "kicad")
SYMDIR = os.path.join(KICAD_SHARE, "symbols")

_tok = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+')


def parse(text):
    """S-expression -> nested lists; atoms stay strings (quoted strings keep their quotes)."""
    stack = [[]]
    for m in _tok.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            node = stack.pop()
            stack[-1].append(node)
        else:
            stack[-1].append(t)
    return stack[0]


def dump(node, indent=0):
    """nested lists -> S-expression text (KiCad style, one node per line)."""
    if isinstance(node, str):
        return node
    simple = all(isinstance(x, str) for x in node)
    if simple:
        return "(" + " ".join(node) + ")"
    out = "(" + (node[0] if isinstance(node[0], str) else dump(node[0], indent + 1))
    for x in node[1:]:
        if isinstance(x, str):
            out += " " + x
        else:
            out += "\n" + "\t" * (indent + 1) + dump(x, indent + 1)
    out += "\n" + "\t" * indent + ")"
    return out


def unq(s):
    return s[1:-1] if len(s) >= 2 and s[0] == '"' else s


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def children(node, key):
    return [x for x in node[1:] if isinstance(x, list) and x and x[0] == key]


def child(node, key):
    c = children(node, key)
    return c[0] if c else None


class Library:
    _cache = {}

    def __init__(self, name):
        self.name = name
        path = os.path.join(SYMDIR, name + ".kicad_sym")
        with open(path, encoding="utf-8") as f:
            self.root = parse(f.read())[0]
        self.symbols = {unq(s[1]): s for s in children(self.root, "symbol")}

    @classmethod
    def get(cls, name):
        if name not in cls._cache:
            cls._cache[name] = cls(name)
        return cls._cache[name]

    def flat(self, symname):
        """Symbol with `extends` resolved: parent's drawing units renamed, child's properties applied."""
        sym = self.symbols[symname]
        ext = child(sym, "extends")
        if not ext:
            return sym
        parent = self.flat(unq(ext[1]))
        pname = unq(parent[1])
        out = ["symbol", q(symname)]
        child_props = {unq(p[1]): p for p in children(sym, "property")}
        for x in parent[2:]:
            if not isinstance(x, list):
                continue
            if x[0] == "property":
                out.append(child_props.get(unq(x[1]), x))
            elif x[0] == "symbol":
                unit = unq(x[1])
                assert unit.startswith(pname + "_"), (unit, pname)
                out.append(["symbol", q(symname + unit[len(pname):])] + x[2:])
            elif x[0] in ("extends",):
                continue
            else:
                out.append(x)
        return out


def pins(flat_sym):
    """[(number, name, x, y, angle, length, type)] with lib coordinates (y up)."""
    res = []
    for unit in children(flat_sym, "symbol"):
        for p in children(unit, "pin"):
            at = child(p, "at")
            res.append((unq(child(p, "number")[1]), unq(child(p, "name")[1]),
                        float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                        float(child(p, "length")[1]), p[1]))
    return res


def load(lib_id):
    lib, name = lib_id.split(":", 1)
    return Library.get(lib).flat(name)


if __name__ == "__main__":
    for lib_id in sys.argv[1:]:
        s = load(lib_id)
        print(lib_id, "units:", [unq(u[1]) for u in children(s, "symbol")],
              "footprint:", unq(child(s, "property") and next((unq(p[2]) for p in children(s, "property") if unq(p[1]) == "Footprint"), "")))
        for n, nm, x, y, a, ln, t in pins(s):
            print(f"   pin {n:>3} {nm:<10} at ({x:7.2f},{y:7.2f}) angle {a:5.0f} len {ln:4.2f} {t}")
