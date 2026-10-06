#!/usr/bin/env python3
"""Drive an OpenPLC v3 runtime on a board from the PC, no browser needed:
login, compile a program, start the PLC, then talk Modbus TCP to it.

    python openplc-test.py 192.168.200.105                      # compile blank_program.st, start, read
    python openplc-test.py 192.168.200.105 --program my.st      # upload + compile my.st first
    python openplc-test.py 192.168.200.105 --no-compile         # just start + Modbus read
    python openplc-test.py 192.168.200.105 --write-coil 0 1     # set %QX0.0
    python openplc-test.py 192.168.200.105 --autostart on --only-settings   # run the program at boot

Only the standard library is used (urllib + raw Modbus TCP frames). Default credentials
openplc/openplc, web on :8080, Modbus on :502.
"""
import argparse
import http.cookiejar
import os
import re
import socket
import struct
import sys
import time
import urllib.parse
import urllib.request
import uuid


def hidden_field(html, name):
    """value of <input ... name='NAME' ... value='...'> (either attribute order)"""
    for m in re.finditer(r"<input[^>]*>", html, re.I):
        tag = m.group(0)
        if re.search(rf"""name=['"]{name}['"]""", tag):
            v = re.search(r"""value=['"]([^'"]*)['"]""", tag)
            return v.group(1) if v else ""
    return ""


class Web:
    def __init__(self, host, port=8080):
        self.base = f"http://{host}:{port}"
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path, timeout=30):
        with self.op.open(self.base + path, timeout=timeout) as r:
            return r.read().decode(errors="replace")

    def post(self, path, data, timeout=30):
        body = urllib.parse.urlencode(data).encode()
        with self.op.open(urllib.request.Request(self.base + path, data=body), timeout=timeout) as r:
            return r.read().decode(errors="replace")

    def post_multipart(self, path, fields, filename, content, timeout=60):
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in fields.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                     f"Content-Type: application/octet-stream\r\n\r\n".encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        req = urllib.request.Request(self.base + path, data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with self.op.open(req, timeout=timeout) as r:
            return r.read().decode(errors="replace")

    def login(self, user="openplc", password="openplc"):
        html = self.post("/login", {"username": user, "password": password})
        if "Bad credentials" in html:
            raise SystemExit("login failed")
        print("web: logged in")

    def compile(self, st_name, timeout=600):
        print(f"web: compiling {st_name} (g++ on the board, this takes a while)...")
        self.get(f"/compile-program?file={st_name}")
        t0 = time.time()
        last = ""
        while time.time() - t0 < timeout:
            log = self.get("/compilation-logs")
            if log != last:
                for line in log[len(last):].splitlines():
                    print("   | " + line)
                last = log
            if "Compilation finished successfully!" in log:
                print(f"web: compiled in {time.time() - t0:.0f} s")
                return True
            if "Compilation finished with errors!" in log or "Error" in log.splitlines()[-1:] :
                if "finished with errors" in log:
                    raise SystemExit("compilation failed")
            time.sleep(3)
        raise SystemExit("compilation timeout")

    def start(self):
        self.get("/start_plc")
        time.sleep(3)
        html = self.get("/dashboard")
        status = "Running" if "Running" in html else "Stopped?"
        print(f"web: start_plc sent, dashboard says {status}")

    def stop(self):
        self.get("/stop_plc")

    def set_autostart(self, enable):
        """Settings -> 'Start OpenPLC in RUN mode' (the runtime starts the active program at boot).
        The form must be posted whole: a missing port field disables that server, and a
        device_hostname different from the current one makes the server call hostnamectl."""
        html = self.get("/settings")

        def checked(id_):
            m = re.search(rf"""<input[^>]*id=['"]{id_}['"][^>]*>""", html, re.I)
            return bool(m and "checked" in m.group(0))

        form = {"device_hostname": hidden_field(html, "device_hostname"),
                "auto_run_text": "true" if enable else "false",
                "snap7_run_text": hidden_field(html, "snap7_run_text") or "false",
                "slave_polling_period": hidden_field(html, "slave_polling_period") or "100",
                "slave_timeout": hidden_field(html, "slave_timeout") or "1000"}
        for box, field in (("modbus_server", "modbus_server_port"), ("dnp3_server", "dnp3_server_port"),
                           ("enip_server", "enip_server_port"), ("pstorage_thread", "pstorage_thread_poll")):
            if checked(box):
                form[field] = hidden_field(html, field)
        self.post("/settings", form)
        html = self.get("/settings")
        state = hidden_field(html, "auto_run_text")
        print(f"web: start in run mode = {state}")
        if state != ("true" if enable else "false"):
            raise SystemExit("settings did not change")


class Modbus:
    def __init__(self, host, port=502, unit=1):
        self.s = socket.create_connection((host, port), timeout=5)
        self.unit = unit
        self.tid = 0

    def req(self, pdu):
        self.tid = (self.tid + 1) & 0xFFFF
        frame = struct.pack(">HHHB", self.tid, 0, len(pdu) + 1, self.unit) + pdu
        self.s.sendall(frame)
        hdr = self.s.recv(7)
        tid, _, length, unit = struct.unpack(">HHHB", hdr)
        data = self.s.recv(length - 1)
        if data[0] & 0x80:
            raise RuntimeError(f"modbus exception 0x{data[1]:02x} for function 0x{data[0] & 0x7f:02x}")
        return data

    def read_coils(self, addr, n):
        d = self.req(struct.pack(">BHH", 1, addr, n))
        bits = []
        for i in range(n):
            bits.append((d[2 + i // 8] >> (i % 8)) & 1)
        return bits

    def read_discrete(self, addr, n):
        d = self.req(struct.pack(">BHH", 2, addr, n))
        return [(d[2 + i // 8] >> (i % 8)) & 1 for i in range(n)]

    def read_holding(self, addr, n):
        d = self.req(struct.pack(">BHH", 3, addr, n))
        return list(struct.unpack(f">{n}H", d[2:2 + 2 * n]))

    def read_input(self, addr, n):
        d = self.req(struct.pack(">BHH", 4, addr, n))
        return list(struct.unpack(f">{n}H", d[2:2 + 2 * n]))

    def write_coil(self, addr, val):
        self.req(struct.pack(">BHH", 5, addr, 0xFF00 if val else 0))

    def write_holding(self, addr, val):
        self.req(struct.pack(">BHH", 6, addr, val & 0xFFFF))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("--program", help=".st file to upload and compile")
    ap.add_argument("--st-name", default="blank_program.st", help="existing st_files/ name to compile")
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--no-start", action="store_true")
    ap.add_argument("--write-coil", nargs=2, type=int, metavar=("ADDR", "VAL"))
    ap.add_argument("--write-holding", nargs=2, type=int, metavar=("ADDR", "VAL"))
    ap.add_argument("--autostart", choices=("on", "off"), help="start the active program at boot (Settings)")
    ap.add_argument("--only-settings", action="store_true", help="change settings and exit")
    a = ap.parse_args()

    w = Web(a.host)
    w.login()
    if a.autostart:
        w.set_autostart(a.autostart == "on")
        if a.only_settings:
            return
    st = a.st_name
    if a.program:
        with open(a.program, "rb") as f:
            content = f.read()
        # same two steps as the browser: /upload-program stores the file as st_files/<random>.st and
        # returns a form whose hidden fields name it; /upload-program-action records it in the DB
        html = w.post_multipart("/upload-program", {}, os.path.basename(a.program), content)
        st = hidden_field(html, "prog_file")
        epoch = hidden_field(html, "epoch_time") or str(int(time.time()))
        if not st:
            raise SystemExit("upload failed: no prog_file in the server's reply\n" + html[-600:])
        w.post(("/upload-program-action"), {"prog_name": os.path.basename(a.program), "prog_descr": "openplc-test.py",
                                             "prog_file": st, "epoch_time": epoch})
        print(f"web: uploaded {a.program} as {st}")
    if not a.no_compile:
        w.compile(st)
    if not a.no_start:
        w.start()

    print("modbus: connecting to :502 ...")
    for attempt in range(10):
        try:
            mb = Modbus(a.host)
            break
        except OSError as ex:
            if attempt == 9:
                raise SystemExit(f"modbus connect failed: {ex}")
            time.sleep(2)
    if a.write_coil:
        mb.write_coil(a.write_coil[0], a.write_coil[1]); print(f"modbus: coil {a.write_coil[0]} <- {a.write_coil[1]}")
    if a.write_holding:
        mb.write_holding(a.write_holding[0], a.write_holding[1]); print(f"modbus: holding {a.write_holding[0]} <- {a.write_holding[1]}")
    for name, fn in (("coils %QX0.0..", lambda: mb.read_coils(0, 8)),
                     ("discrete %IX0.0..", lambda: mb.read_discrete(0, 8)),
                     ("holding %QW0..", lambda: mb.read_holding(0, 4)),
                     ("input %IW0..", lambda: mb.read_input(0, 4))):
        try:
            print(f"modbus: {name:20s} {fn()}")
        except Exception as ex:  # noqa: BLE001
            print(f"modbus: {name:20s} {ex}")


if __name__ == "__main__":
    main()
