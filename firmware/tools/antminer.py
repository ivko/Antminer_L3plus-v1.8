#!/usr/bin/env python3
"""PC-side tool for the Antminer BB-Black I/O module (Windows and Linux).

    python antminer.py config                         # show the effective settings
    python antminer.py console "uname -a"             # run a shell command on the board's serial console
    python antminer.py uboot "printenv" "nand bad"    # reboot, stop U-Boot, run commands (--then boot|stay)
    python antminer.py netboot                        # boot kernel/DTB/initramfs from firmware/out over TFTP (RAM only)
    python antminer.py netboot --dtb am335x-antminer-breakout.dtb --log boot.log
    python antminer.py deploy-dtb breakout            # build the profile's DTB, write it to mtd6, reboot
    python antminer.py deploy-dtb breakout --netboot-only
    python antminer.py feed start|stop|status|serve   # opkg feed (HTTP) from the Yocto deploy directory
    python antminer.py tftp                           # TFTP server for firmware/out in the foreground
    python antminer.py stage                          # copy build results into firmware/out (tools/stage-out.sh)

Settings come from tools/site.conf, tools/site.local.conf (per machine, not in git) and
environment variables ANTMINER_<KEY>. Needs Python 3.8+ and pyserial (pip install pyserial)
for the serial commands. Nothing here writes outside mtd6..mtd8; see docs/03-install.md.
"""
import argparse
import importlib.util
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import threading
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.dirname(TOOLS)
OUT = os.path.join(MAIN, "out")
IS_WIN = platform.system() == "Windows"
ESC, CTRL_C = "\x1b", "\x03"

# ---------------------------------------------------------------------------------------------
# settings


def load_config():
    cfg = {}
    for name in ("site.conf", "site.local.conf"):
        path = os.path.join(TOOLS, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    for k in list(cfg) + ["PC_IP", "SERIAL_PORT", "FEED_PORT", "YOCTO_DIR", "BOARD_PASSWORD"]:
        if f"ANTMINER_{k}" in os.environ:
            cfg[k] = os.environ[f"ANTMINER_{k}"]
    cfg.setdefault("SERIAL_PORT", "COM3" if IS_WIN else "/dev/ttyUSB0")
    cfg.setdefault("FEED_PORT", "8000")
    cfg.setdefault("YOCTO_DIR", "~/antminer/yocto")
    cfg.setdefault("BOARD_PASSWORD", "")
    if not cfg.get("PC_IP"):
        cfg["PC_IP"] = detect_ip()
    return cfg


def detect_ip():
    """IP of the interface with the default route (no packet is sent)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ---------------------------------------------------------------------------------------------
# WSL / Linux helpers


def run_unix(cmd, check=True):
    """run a bash command line on Linux, or inside WSL on Windows; returns (rc, output)"""
    argv = (["wsl", "bash", "-lc", cmd] if IS_WIN else ["bash", "-lc", cmd])
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", errors="replace").replace("\0", "")
    if check and p.returncode != 0:
        sys.stdout.write(out)
        sys.exit(f"command failed ({p.returncode}): {cmd}")
    return p.returncode, out


def unix_path(path):
    """a local path as bash sees it (wslpath on Windows)"""
    if not IS_WIN:
        return path
    return run_unix(f"wslpath -a '{path.replace(os.sep, '/')}'")[1].strip()


def deploy_dir(cfg):
    """the Yocto deploy directory as a path this Python can open"""
    yd = cfg["YOCTO_DIR"]
    if not IS_WIN:
        return os.path.join(os.path.expanduser(yd), "build", "tmp", "deploy")
    home = run_unix("echo $HOME")[1].strip()
    linux = yd.replace("~", home, 1) + "/build/tmp/deploy"
    distro = subprocess.run(["wsl", "-l", "-q"], stdout=subprocess.PIPE).stdout.decode("utf-16-le", errors="ignore")
    distro = next((d.strip() for d in distro.splitlines() if d.strip()), "Ubuntu")
    return "\\\\wsl$\\" + distro + linux.replace("/", "\\")


# ---------------------------------------------------------------------------------------------
# TFTP (reuses tftp-server.py)


def _tftp_module():
    spec = importlib.util.spec_from_file_location("tftp_server", os.path.join(TOOLS, "tftp-server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def udp_port_busy(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("0.0.0.0", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


class TftpThread(threading.Thread):
    """TFTP server for a directory, in a background thread; does nothing if UDP 69 is taken"""

    def __init__(self, root, port=69):
        super().__init__(daemon=True)
        self.root, self.port, self.stop = os.path.realpath(root), port, threading.Event()
        self.started_here = False

    def start(self):
        if udp_port_busy(self.port):
            print(f"[tftp] UDP {self.port} already in use, assuming a TFTP server serves {self.root}")
            return self
        self.started_here = True
        super().start()
        print(f"[tftp] serving {self.root} on UDP {self.port}")
        return self

    def run(self):
        t = _tftp_module()
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("0.0.0.0", self.port))
        srv.settimeout(0.5)
        while not self.stop.is_set():
            try:
                data, addr = srv.recvfrom(2048)
            except socket.timeout:
                continue
            if len(data) >= 4 and data[:2] == b"\x00\x01":
                fn, _mode, opts = t.parse_rrq(data)
                threading.Thread(target=t.serve_file, args=(self.root, addr, fn, opts), daemon=True).start()
        srv.close()


# ---------------------------------------------------------------------------------------------
# serial console


class Console:
    UBOOT_PROMPT = re.compile(r"U-Boot# $")
    SHELL_PROMPT = re.compile(r"(# |\$ )$")
    LOGIN_PROMPT = re.compile(r"login: $")

    def __init__(self, port, password="", echo=True, log=None):
        try:
            import serial  # pyserial
        except ImportError:
            sys.exit("pyserial is missing: pip install pyserial")
        self.sp = serial.Serial(port, 115200, timeout=0.05)
        self.sp.dtr = False
        self.sp.rts = False
        self.password, self.echo, self.log = password, echo, log
        self.tail = ""
        self.buf = []

    def close(self):
        self.sp.close()

    def write(self, s):
        self.sp.write(s.encode("latin-1"))

    def pump(self):
        data = self.sp.read(65536)
        if not data:
            return 0
        s = data.decode("utf-8", errors="replace")
        self.buf.append(s)
        if self.log:
            self.log.write(s)
        if self.echo:
            sys.stdout.write(s)
            sys.stdout.flush()
        # U-Boot echoes ESC bytes; keep them (and NULs) out of the prompt matching
        self.tail = (self.tail + s.replace(ESC, "").replace("\0", ""))[-4000:]
        return len(s)

    def wait_for(self, regex, timeout, while_fn=None):
        rx = re.compile(regex) if isinstance(regex, str) else regex
        end = time.time() + timeout
        while time.time() < end:
            self.pump()
            if rx.search(self.tail):
                return True
            if while_fn:
                while_fn()
        return False

    def settle(self, seconds=0.8):
        end = time.time() + seconds
        while time.time() < end:
            self.pump()

    # -- Linux shell -------------------------------------------------------------------------
    def login(self):
        """make sure a root shell prompt is there; returns False if the board is in U-Boot"""
        self.tail = ""
        self.write("\r")
        self.settle(1.0)
        if not self.tail.strip():
            self.write("\r")
            self.settle(2.0)
            if not self.tail.strip():
                sys.exit("no answer on the serial console (board off? TX/RX swapped? wrong port?)")
        if self.UBOOT_PROMPT.search(self.tail):
            return False
        if self.LOGIN_PROMPT.search(self.tail):
            self.tail = ""
            self.write("root\r")
            if self.wait_for(r"(Password: $|# $)", 5) and self.tail.rstrip().endswith("Password:"):
                self.write(self.password + "\r")
            if not self.wait_for(self.SHELL_PROMPT, 10):
                sys.exit("login failed (check BOARD_PASSWORD)")
        return True

    def shell(self, cmd, timeout=60, marker=None):
        """run a command; returns its output (between the echo and the next prompt)"""
        tag = f"__ANTMINER_DONE_{int(time.time())}__"
        self.tail = ""
        start = len("".join(self.buf))
        self.write(f"{cmd}; echo {tag}=$?\r")
        if not self.wait_for(re.compile(re.escape(tag) + r"=(\d+)\s*\r?\n.*(# |\$ )$", re.S), timeout):
            raise TimeoutError(f"no prompt after '{cmd}' within {timeout}s")
        out = "".join(self.buf)[start:]
        m = re.search(re.escape(tag) + r"=(\d+)", out.split("\n", 1)[-1])
        body = out.split("\n", 1)[-1]
        body = body[: body.rfind(tag)] if tag in body else body
        return int(m.group(1)) if m else -1, body.replace("\r", "")

    # -- U-Boot ------------------------------------------------------------------------------
    def to_uboot(self):
        """reboot whatever runs and stop U-Boot's autoboot"""
        self.tail = ""
        self.write("\r")
        self.settle(0.8)
        if self.UBOOT_PROMPT.search(self.tail):
            print("\n[uboot] already at the prompt")
            return
        if self.LOGIN_PROMPT.search(self.tail):
            self.login()
        print("\n[uboot] rebooting and waiting for U-Boot...")
        # a bare init=/bin/sh from an old netboot has no init to talk to: -f
        self.write("reboot\r" if re.search(r"@\S+:.*# $", self.tail) else "reboot -f\r")
        if not self.wait_for(r"U-Boot 2013\.04|U-Boot SPL|Press ESC", 120):
            sys.exit("no U-Boot banner within 120 s (is the board powered and on this port?)")
        if not self.wait_for(self.UBOOT_PROMPT, 30, lambda: self.write(ESC)):
            sys.exit("could not stop autoboot")
        # the ESC bytes sit in U-Boot's line buffer: Ctrl-C drops the line
        time.sleep(0.3)
        self.tail = ""
        self.write(CTRL_C)
        self.wait_for(self.UBOOT_PROMPT, 5)
        for _ in range(2):
            self.uboot("", 5, check=False)
        print("\n[uboot] at the prompt")

    def uboot(self, cmd, timeout=30, check=True):
        self.tail = ""
        self.write(cmd + "\r")
        if not self.wait_for(self.UBOOT_PROMPT, timeout):
            if check:
                raise RuntimeError(f"U-Boot: no prompt after '{cmd}' within {timeout}s")
            return False
        if check and re.search(r"Retry count exceeded|Not retrying|TFTP error|ERROR|Bad Magic|Wrong Image", self.tail):
            raise RuntimeError(f"U-Boot reported an error after '{cmd}'")
        return True


def open_console(cfg, args, echo=True):
    log = open(args.log, "w", encoding="utf-8", newline="") if getattr(args, "log", None) else None
    try:
        return Console(args.port or cfg["SERIAL_PORT"], cfg["BOARD_PASSWORD"], echo=echo, log=log)
    except Exception as ex:  # noqa: BLE001
        sys.exit(f"cannot open {args.port or cfg['SERIAL_PORT']}: {ex}\n"
                 "(another program such as PuTTY holds it? wrong port? set SERIAL_PORT in tools/site.local.conf)")


# ---------------------------------------------------------------------------------------------
# commands


def cmd_config(cfg, args):
    for k in ("PC_IP", "SERIAL_PORT", "FEED_PORT", "YOCTO_DIR", "BOARD_PASSWORD"):
        print(f"{k:15s} {cfg.get(k, '')}")
    print(f"{'out dir':15s} {OUT}")
    print(f"{'feed dir':15s} {deploy_dir(cfg)}")


def cmd_console(cfg, args):
    c = open_console(cfg, args, echo=False)
    try:
        if not c.login():
            sys.exit("the board is at the U-Boot prompt, not in Linux")
        rc, out = c.shell(" ".join(args.command), timeout=args.timeout)
        sys.stdout.write(out)
        sys.exit(rc)
    finally:
        c.close()


def cmd_uboot(cfg, args):
    c = open_console(cfg, args)
    try:
        c.to_uboot()
        for command in args.commands:
            c.uboot(command, args.timeout)
        if args.then == "boot":
            print("\n[uboot] continuing the normal boot")
            c.tail = ""
            c.write("boot\r")
            c.wait_for(Console.LOGIN_PROMPT, args.boot_log)
    finally:
        c.close()


def netboot(cfg, args, kernel, dtb, initrd, bootargs, log_seconds):
    for f in (kernel, dtb, initrd):
        if not os.path.exists(os.path.join(OUT, f)):
            sys.exit(f"missing {os.path.join(OUT, f)} (run: python antminer.py stage)")
    tftp = TftpThread(OUT).start()
    c = open_console(cfg, args)
    try:
        c.to_uboot()
        c.uboot("setenv autoload no")
        c.uboot(f"setenv serverip {cfg['PC_IP']}")
        if args.board_ip:
            c.uboot(f"setenv ipaddr {args.board_ip}")
        else:
            c.uboot("dhcp", 60)
            if "DHCP client bound to address" not in c.tail:
                sys.exit("DHCP failed; retry with --board-ip")
        c.uboot("printenv ipaddr serverip ethaddr")
        # addresses as in sdcard/uEnv.txt
        c.uboot(f"tftp 0x82000000 {kernel}", 180)
        c.uboot(f"tftp 0x88000000 {dtb}", 60)
        c.uboot(f"tftp 0x88100000 {initrd}", 300)
        c.uboot("iminfo 0x82000000")
        c.uboot(f"setenv bootargs {bootargs}")
        c.tail = ""
        c.write("bootm 0x82000000 0x88100000 0x88000000\r")
        print(f"\n[netboot] bootm sent, kernel log for up to {log_seconds} s")
        c.wait_for(r"(login: |/ # )$", log_seconds)
        print("\n[netboot] done (running from RAM; a reboot returns to NAND)")
    finally:
        c.close()
        tftp.stop.set()


def cmd_netboot(cfg, args):
    netboot(cfg, args, args.kernel, args.dtb, args.initrd, args.bootargs, args.wait)


def build_dtb(profile):
    pinmux = unix_path(os.path.join(MAIN, "pinmux"))
    print(f"[dtb] building pinmux/boards/{profile}.yaml")
    _rc, out = run_unix(f"cd '{pinmux}' && bash build-dtb.sh boards/{profile}.yaml 2>&1")
    for line in out.splitlines():
        if re.search(r"wrote|dtb:|error", line):
            print("   " + line)
    dtb = f"am335x-antminer-{profile}.dtb"
    if not os.path.exists(os.path.join(OUT, dtb)):
        sys.exit(f"no {dtb} in {OUT}")
    return dtb


def cmd_deploy_dtb(cfg, args):
    dtb = build_dtb(args.profile)
    if args.netboot_only:
        netboot(cfg, args, "uImage-yocto.bin", dtb, "antminer-image.cpio.gz.u-boot", "console=ttyS0,115200n8", 60)
        return
    import shutil
    shutil.copy(os.path.join(TOOLS, "flash-nand.sh"), os.path.join(OUT, "flash-nand.sh"))
    tftp = TftpThread(OUT).start()
    c = open_console(cfg, args, echo=False)
    try:
        if not c.login():
            sys.exit("the board is at the U-Boot prompt; boot Linux first")
        ip = cfg["PC_IP"]
        rc, out = c.shell(f"cd /tmp && tftp -g -r flash-nand.sh {ip} && sh flash-nand.sh --dtb-only {ip} {dtb}", 120)
        print(out)
        if rc != 0 or "verified" not in out:
            sys.exit("flashing failed")
        if not args.no_reboot:
            print("[dtb] rebooting into the new device tree")
            c.echo = True
            c.tail = ""
            c.write("reboot\r")
            c.wait_for(Console.LOGIN_PROMPT, 120)
    finally:
        c.close()
        tftp.stop.set()


def _pidfile():
    return os.path.join(OUT, ".feed-server.pid")


def cmd_feed(cfg, args):
    root = deploy_dir(cfg)
    port = int(cfg["FEED_PORT"])
    if args.action == "serve":
        if not os.path.isdir(os.path.join(root, "ipk")):
            sys.exit(f"no ipk feed in {root} (build first: bash firmware/yocto/build.sh)")
        print(f"[feed] http://{cfg['PC_IP']}:{port}/ipk/  serving {root}  (Ctrl-C stops)")
        os.chdir(root)
        import http.server
        http.server.ThreadingHTTPServer(("0.0.0.0", port), http.server.SimpleHTTPRequestHandler).serve_forever()
    elif args.action == "start":
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                print(f"[feed] something already listens on TCP {port}")
                return
        kw = {"creationflags": 0x08000000} if IS_WIN else {"start_new_session": True}   # CREATE_NO_WINDOW
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "feed", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        os.makedirs(OUT, exist_ok=True)
        with open(_pidfile(), "w") as fh:
            fh.write(str(p.pid))
        time.sleep(2)
        if p.poll() is not None:
            sys.exit("feed server exited immediately (run 'feed serve' to see why)")
        print(f"[feed] started (pid {p.pid}): http://{cfg['PC_IP']}:{port}/ipk/")
    elif args.action == "stop":
        if not os.path.exists(_pidfile()):
            print("[feed] not started by this tool")
            return
        pid = int(open(_pidfile()).read())
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        os.unlink(_pidfile())
        print(f"[feed] stopped (pid {pid})")
    else:
        with socket.socket() as s:
            up = s.connect_ex(("127.0.0.1", port)) == 0
        print(f"[feed] TCP {port}: {'listening' if up else 'not listening'}; root {root}")


def cmd_tftp(cfg, args):
    t = TftpThread(args.root or OUT).start()
    if not t.started_here:
        return
    print("[tftp] Ctrl-C stops")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        t.stop.set()


def cmd_stage(cfg, args):
    script = unix_path(os.path.join(TOOLS, "stage-out.sh"))
    _rc, out = run_unix(f"Y={cfg['YOCTO_DIR']} bash '{script}'")
    print(out)


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help=f"serial port (default from site.conf: {cfg['SERIAL_PORT']})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config", help="show the effective settings").set_defaults(fn=cmd_config)

    p = sub.add_parser("console", help="run a shell command on the board over the serial console")
    p.add_argument("command", nargs="+")
    p.add_argument("--timeout", type=int, default=60)
    p.set_defaults(fn=cmd_console)

    p = sub.add_parser("uboot", help="reboot into U-Boot and run commands")
    p.add_argument("commands", nargs="*")
    p.add_argument("--then", choices=("boot", "stay"), default="stay")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--boot-log", type=int, default=60)
    p.add_argument("--log")
    p.set_defaults(fn=cmd_uboot)

    p = sub.add_parser("netboot", help="boot from firmware/out over TFTP, nothing is written")
    p.add_argument("--kernel", default="uImage-yocto.bin")
    p.add_argument("--dtb", default="am335x-antminer-yocto.dtb")
    p.add_argument("--initrd", default="antminer-image.cpio.gz.u-boot")
    p.add_argument("--bootargs", default="console=ttyS0,115200n8")
    p.add_argument("--board-ip", help="static IP for U-Boot instead of DHCP")
    p.add_argument("--wait", type=int, default=90, help="seconds of kernel log to show")
    p.add_argument("--log")
    p.set_defaults(fn=cmd_netboot)

    p = sub.add_parser("deploy-dtb", help="build a pinmux profile and write it to mtd6")
    p.add_argument("profile")
    p.add_argument("--netboot-only", action="store_true")
    p.add_argument("--no-reboot", action="store_true")
    p.add_argument("--board-ip")
    p.add_argument("--log")
    p.set_defaults(fn=cmd_deploy_dtb)

    p = sub.add_parser("feed", help="opkg feed HTTP server")
    p.add_argument("action", choices=("start", "stop", "status", "serve"))
    p.set_defaults(fn=cmd_feed)

    p = sub.add_parser("tftp", help="TFTP server (foreground)")
    p.add_argument("--root")
    p.set_defaults(fn=cmd_tftp)

    sub.add_parser("stage", help="copy build results to firmware/out").set_defaults(fn=cmd_stage)

    args = ap.parse_args()
    args.fn(cfg, args)


if __name__ == "__main__":
    main()
