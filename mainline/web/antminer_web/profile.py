"""Pinmux profile: YAML file <-> JSON model used by the board editor.

model = {"name": str, "pins": {"P8.43": {"func", "dir", "init", "pull", "name", "hog", "comment"}},
         "adc": [0, 1, ...], "i2c": {...}, "spi": {...}, "unused": "default", "extra": {other keys}}
The YAML written back is generated (hand comments are lost) but each pin's `comment:` field is
kept and also emitted as an end-of-line comment, so notes survive both editors.
"""
import os
import re

import yaml

PIN_KEYS = ("func", "dir", "init", "pull", "rx", "slew", "name", "hog", "comment")
TOP_KEYS = ("name", "pins", "adc", "i2c", "spi", "pwm", "can", "uart", "unused")


def load(text):
    doc = yaml.safe_load(text) or {}
    if not isinstance(doc, dict):
        raise ValueError("profile must be a mapping")
    pins = {}
    for key, spec in (doc.get("pins") or {}).items():
        if isinstance(spec, str):
            spec = {"func": spec}
        if not isinstance(spec, dict):
            continue
        p = {"func": str(spec.get("func", "gpio")).lower()}
        for k in PIN_KEYS[1:]:
            if k in spec and spec[k] is not None:
                p[k] = spec[k]
        pins[str(key)] = p
    model = {"name": str(doc.get("name", "custom")), "pins": pins,
             "adc": [int(c) for c in (doc.get("adc") or [])],
             "unused": str(doc.get("unused", "default"))}
    for k in ("i2c", "spi", "pwm", "can", "uart"):
        if doc.get(k):
            model[k] = doc[k]
    model["extra"] = {k: v for k, v in doc.items() if k not in TOP_KEYS}
    return model


def _pin_key_order(k):
    m = re.match(r"P(\d)\.(\d+)$", k)
    return (0, int(m.group(1)), int(m.group(2))) if m else (1, 0, k)


def _scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v)
    return s if re.match(r"^[A-Za-z0-9_./+-]+$", s) else yaml.safe_dump(s, default_flow_style=True).strip()


def dump(model):
    """model -> YAML text, pins grouped by header, one line per pin"""
    out = [f"name: {_scalar(model.get('name', 'custom'))}", ""]
    pins = model.get("pins") or {}
    if pins:
        out.append("pins:")
        last_hdr = None
        for key in sorted(pins, key=_pin_key_order):
            hdr = key.split(".")[0] if key.startswith("P") else "other pads"
            if hdr != last_hdr:
                out.append(f"  # --- {hdr} ---")
                last_hdr = hdr
            p = pins[key]
            if isinstance(p, str):            # shorthand "P9.24: uart1_txd" straight from JSON
                p = {"func": p}
            if not isinstance(p, dict):
                raise ValueError(f"pin {key}: spec must be a string or a mapping")
            comment = p.get("comment")
            # keep 0 (init: 0 matters), drop None / "" / false flags
            fields = {k: p[k] for k in PIN_KEYS
                      if k in p and k != "comment" and p[k] is not None and p[k] != ""
                      and not (isinstance(p[k], bool) and not p[k])}
            if list(fields) == ["func"]:
                body = _scalar(fields["func"])
            else:
                body = "{" + ", ".join(f"{k}: {_scalar(v)}" for k, v in fields.items()) + "}"
            line = f"  {key}: {body}"
            if comment:
                line = f"{line:<52s} # {str(comment).replace(chr(10), ' ')}"
            out.append(line)
        out.append("")
    adc = model.get("adc") or []
    out.append("adc: [" + ", ".join(str(int(c)) for c in adc) + "]")
    for k in ("i2c", "spi", "pwm", "can", "uart"):
        if model.get(k):
            out.append("")
            out.append(yaml.safe_dump({k: model[k]}, default_flow_style=False, sort_keys=False).rstrip())
    if str(model.get("unused", "default")) != "default":
        out.append(f"unused: {model['unused']}")
    for k, v in (model.get("extra") or {}).items():
        out.append(yaml.safe_dump({k: v}, default_flow_style=False, sort_keys=False).rstrip())
    return "\n".join(out).rstrip() + "\n"


def roundtrip_ok(text):
    """sanity: dump(load(text)) parses back to the same pins/adc"""
    a = load(text)
    b = load(dump(a))
    return a["pins"] == b["pins"] and a["adc"] == b["adc"]
