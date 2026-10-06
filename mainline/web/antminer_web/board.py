"""Read-only facts about the board: identity, boot order, NAND contents vs the SD payload."""
import glob
import hashlib
import os
import re
import struct
import time

from .jobs import run_quick

PAYLOAD_DIR = os.environ.get("ANTMINER_PAYLOAD", "/boot")
CONFIG_DIR = os.environ.get("ANTMINER_CONFIG", "/config")
PINMUX_DIR = os.environ.get("ANTMINER_PINMUX", "/usr/share/antminer/pinmux")   # host dev: repo/mainline/pinmux

# TRM table 26-7 (AM335x), the rows we have met
SYSBOOT_SEQ = {
    0b10011: "NAND, NANDI2C, MMC0, UART0",
    0b10111: "MMC0, SPI0, UART0, USB0",
    0b11100: "MMC1, MMC0, UART0, USB0",
    0b11000: "SPI0, MMC0, USB0, UART0",
}


def read(path, default=""):
    try:
        with open(path, "rb") as fh:
            return fh.read().replace(b"\0", b"").decode(errors="replace").strip()
    except OSError:
        return default


def identity():
    mac = read("/sys/class/net/eth0/address")
    model = read("/proc/device-tree/model")
    m = re.search(r"profile (\S+)", model)
    cmdline = read("/proc/cmdline")
    if "antminer.root=sd" in cmdline:
        root = "SD card (provisioning system)"
    elif re.search(r"overlay / ", read("/proc/mounts")):
        root = "NAND: overlay on ubi0:data"
    else:
        root = "NAND: plain initramfs"
    up = float(read("/proc/uptime", "0 0").split()[0])
    rc, out = run_quick(["devmem", "0x44E10040"])
    sysboot = None
    if rc == 0 and out.strip().startswith("0x"):
        val = int(out.strip(), 16) & 0xFFFF
        seq = val & 0x1F
        sysboot = {"raw": f"0x{val:04x}", "seq_bits": f"{seq:05b}",
                   "order": SYSBOOT_SEQ.get(seq, "see TRM table 26-7")}
    ip = ""
    rc, out = run_quick(["ip", "-4", "-o", "addr", "show", "eth0"])
    if rc == 0:
        m2 = re.search(r"inet (\S+)", out)
        ip = m2.group(1) if m2 else ""
    return {
        "mac": mac, "hostname": read("/etc/hostname") or os.uname().nodename,
        "ip": ip, "model": model, "profile": m.group(1) if m else "?", "root": root,
        "kernel": os.uname().release, "uptime": f"{int(up // 3600)}h {int(up % 3600 // 60)}m",
        "sysboot": sysboot, "time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }


def mtd_table():
    parts = []
    for line in read("/proc/mtd").splitlines()[1:]:
        m = re.match(r'(mtd\d+): (\w+) (\w+) "([^"]+)"', line)
        if m:
            parts.append({"dev": m.group(1), "size": int(m.group(2), 16), "name": m.group(4)})
    return parts


def _nand_read(dev, length):
    pages = (length + 2047) // 2048
    rc, _ = run_quick(["sh", "-c", f"nanddump -q -l {pages * 2048} /dev/{dev} > /tmp/.nand_{dev}"], timeout=120)
    if rc != 0:
        return b""
    with open(f"/tmp/.nand_{dev}", "rb") as fh:
        data = fh.read(length)
    os.unlink(f"/tmp/.nand_{dev}")
    return data


def image_length(head):
    """length of a legacy uImage (64-byte header) or a DTB from its first bytes, else None"""
    if len(head) >= 64 and head[:4] == b"\x27\x05\x19\x56":
        return 64 + struct.unpack(">I", head[12:16])[0]
    if len(head) >= 8 and head[:4] == b"\xd0\x0d\xfe\xed":
        return struct.unpack(">I", head[4:8])[0]
    return None


def nand_contents():
    """what is in fdt / kernel / root: type, length, md5, uImage name"""
    out = {}
    for p in mtd_table():
        if p["name"] not in ("fdt", "kernel", "root"):
            continue
        head = _nand_read(p["dev"], 2048)
        length = image_length(head)
        info = {"dev": p["dev"], "size": p["size"], "length": length, "md5": None, "desc": "empty / unknown"}
        if length and length <= p["size"]:
            data = _nand_read(p["dev"], length)
            info["md5"] = hashlib.md5(data).hexdigest()
            if head[:4] == b"\x27\x05\x19\x56":
                info["desc"] = "uImage: " + head[32:64].split(b"\0")[0].decode(errors="replace")
            else:
                m = re.search(rb"profile ([\w-]+)", data[:8192] + data[-8192:])
                mm = re.search(rb"model\0", data)
                info["desc"] = "DTB" + (f", profile {m.group(1).decode()}" if m else "") + ("" if mm else "")
        out[p["name"]] = info
    return out


def payload_files():
    """files on the boot partition the UI can flash, with md5 (cached per mtime)"""
    files = []
    for path in sorted(glob.glob(os.path.join(PAYLOAD_DIR, "*"))):
        if os.path.isdir(path):
            continue
        name = os.path.basename(path)
        kind = ("kernel" if name.startswith("uImage") else "dtb" if name.endswith(".dtb")
                else "initramfs" if "initramfs" in name or "cpio" in name else "boot" if name in ("MLO", "u-boot.img", "uEnv.txt") else "other")
        files.append({"name": name, "size": os.path.getsize(path), "kind": kind, "md5": _md5_cached(path)})
    return files


_md5_cache = {}


def _md5_cached(path):
    st = os.stat(path)
    key = (path, st.st_mtime, st.st_size)
    if key not in _md5_cache:
        h = hashlib.md5()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _md5_cache[key] = h.hexdigest()
    return _md5_cache[key]


def dtb_profile(path):
    with open(path, "rb") as fh:
        data = fh.read()
    m = re.search(rb"profile ([\w-]+)", data)
    return m.group(1).decode() if m else "?"


def profiles():
    """pinmux profiles: shipped + board-local (/config/pinmux)"""
    out = []
    for base, origin in ((os.path.join(PINMUX_DIR, "boards"), "shipped"), (os.path.join(CONFIG_DIR, "pinmux"), "local")):
        for path in sorted(glob.glob(os.path.join(base, "*.yaml"))):
            out.append({"name": os.path.basename(path)[:-5], "path": path, "origin": origin})
    return out


def data_status():
    rc, out = run_quick(["antminer-data", "status"])
    return out.strip() or f"antminer-data status failed ({rc})"


def sd_card():
    name = read("/sys/block/mmcblk0/device/name")
    if not name:
        return None
    size = int(read("/sys/block/mmcblk0/size", "0")) * 512
    return {"name": name, "size_gb": size / 1e9, "parts": [os.path.basename(p) for p in sorted(glob.glob("/sys/block/mmcblk0/mmcblk0p*"))]}


def config_values():
    net = {"MODE": "dhcp", "ADDRESS": "", "NETMASK": "255.255.255.0", "GATEWAY": "", "DNS": ""}
    for line in read(os.path.join(CONFIG_DIR, "network")).splitlines():
        m = re.match(r"\s*(\w+)=(.*)$", line)
        if m:
            net[m.group(1)] = m.group(2).strip().strip('"')
    return {
        "hostname": read(os.path.join(CONFIG_DIR, "hostname")),
        "ntp": read(os.path.join(CONFIG_DIR, "ntp-server")),
        "net": net,
        "authorized_keys": read(os.path.join(CONFIG_DIR, "ssh", "authorized_keys")),
        "config_mounted": " /config " in read("/proc/mounts"),
    }
