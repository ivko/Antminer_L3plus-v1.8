#!/usr/bin/env python3
"""Minimal read-only TFTP server (RFC 1350 + RFC 2347/2348/2349 options) for netbooting
the Antminer board from U-Boot 2013.04.

    python tftp-server.py --root E:\\Antminer\\repo\\mainline\\out

U-Boot requests blksize 1468 and tsize; both are honoured. Only files inside --root are
served, no writes. Windows Firewall must allow inbound UDP 69 for python.exe:
    netsh advfirewall firewall add rule name="TFTP in" dir=in action=allow protocol=UDP localport=69
"""
import argparse
import os
import socket
import struct
import sys
import threading
import time

OP_RRQ, OP_WRQ, OP_DATA, OP_ACK, OP_ERROR, OP_OACK = 1, 2, 3, 4, 5, 6
MAX_BLKSIZE = 1468
TIMEOUT = 3.0
RETRIES = 6


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


def send_error(sock, addr, code, msg):
    sock.sendto(struct.pack("!HH", OP_ERROR, code) + msg.encode() + b"\0", addr)


def serve_file(root, addr, filename, options):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    try:
        path = os.path.realpath(os.path.join(root, filename.replace("/", os.sep).lstrip(os.sep)))
        if not path.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(path):
            log(f"{addr[0]}: '{filename}' not found")
            send_error(sock, addr, 1, "File not found")
            return
        size = os.path.getsize(path)
        blksize = 512
        oack = {}
        if "blksize" in options:
            blksize = max(8, min(int(options["blksize"]), MAX_BLKSIZE))
            oack["blksize"] = str(blksize)
        if "tsize" in options:
            oack["tsize"] = str(size)
        if "timeout" in options:
            oack["timeout"] = options["timeout"]
        log(f"{addr[0]}: RRQ {filename} ({size} bytes, blksize {blksize})")

        def wait_ack(expect_block):
            for _ in range(RETRIES):
                try:
                    data, peer = sock.recvfrom(1024)
                except socket.timeout:
                    return False
                if peer != addr or len(data) < 4:
                    continue
                op, blk = struct.unpack("!HH", data[:4])
                if op == OP_ERROR:
                    emsg = data[4:].rstrip(b"\0").decode(errors="replace")
                    log(f"{addr[0]}: client error {emsg}")
                    return None
                if op == OP_ACK and blk == expect_block:
                    return True
            return False

        if oack:
            pkt = struct.pack("!H", OP_OACK) + b"".join(k.encode() + b"\0" + v.encode() + b"\0" for k, v in oack.items())
            for _ in range(RETRIES):
                sock.sendto(pkt, addr)
                r = wait_ack(0)
                if r:
                    break
                if r is None:
                    return
            else:
                log(f"{addr[0]}: no ACK for OACK, giving up")
                return

        t0 = time.time()
        with open(path, "rb") as f:
            block = 1
            sent = 0
            while True:
                chunk = f.read(blksize)
                pkt = struct.pack("!HH", OP_DATA, block & 0xFFFF) + chunk
                ok = False
                for _ in range(RETRIES):
                    sock.sendto(pkt, addr)
                    r = wait_ack(block & 0xFFFF)
                    if r:
                        ok = True
                        break
                    if r is None:
                        return
                if not ok:
                    log(f"{addr[0]}: timeout at block {block}, aborting")
                    return
                sent += len(chunk)
                block += 1
                if len(chunk) < blksize:
                    break
        dt = time.time() - t0
        log(f"{addr[0]}: done {filename} {sent} bytes in {dt:.1f}s ({sent / dt / 1024:.0f} KiB/s)")
    finally:
        sock.close()


def parse_rrq(data):
    parts = data[2:].split(b"\0")
    filename = parts[0].decode(errors="replace")
    mode = parts[1].decode(errors="replace").lower() if len(parts) > 1 else "octet"
    opts = {}
    rest = parts[2:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i]:
            opts[rest[i].decode(errors="replace").lower()] = rest[i + 1].decode(errors="replace")
    return filename, mode, opts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=69)
    a = ap.parse_args()
    root = os.path.realpath(a.root)
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind((a.bind, a.port))
    log(f"serving {root} on {a.bind}:{a.port}")
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            log(f"  {name}  {os.path.getsize(p)}")
    while True:
        data, addr = srv.recvfrom(2048)
        if len(data) < 4:
            continue
        op = struct.unpack("!H", data[:2])[0]
        if op == OP_RRQ:
            filename, mode, opts = parse_rrq(data)
            threading.Thread(target=serve_file, args=(root, addr, filename, opts), daemon=True).start()
        elif op == OP_WRQ:
            send_error(srv, addr, 2, "Read-only server")
        # anything else on port 69 is ignored


if __name__ == "__main__":
    main()
