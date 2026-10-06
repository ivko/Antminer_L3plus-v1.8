"""Flask routes. Pages: board, nand, pinmux, services, log. Long operations run as jobs."""
import hashlib
import os
import re
import secrets
import subprocess

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for

import json

from . import __version__, board, profile
from .jobs import run_quick, runner

FLASH = "/usr/sbin/antminer-flash-nand"
DTB = "/usr/sbin/antminer-dtb"
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")
PASSWORD_FILE = os.path.join(board.CONFIG_DIR, "web-password")   # "sha256$<salt>$<hex>"


def password_set():
    return os.path.exists(PASSWORD_FILE) and os.path.getsize(PASSWORD_FILE) > 0


def password_ok(pw):
    try:
        algo, salt, digest = board.read(PASSWORD_FILE).split("$")
    except ValueError:
        return False
    return algo == "sha256" and hashlib.sha256((salt + pw).encode()).hexdigest() == digest


def password_store(pw):
    salt = secrets.token_hex(8)
    with open(PASSWORD_FILE, "w") as fh:
        fh.write(f"sha256${salt}${hashlib.sha256((salt + pw).encode()).hexdigest()}\n")


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 2 << 20

    @app.before_request
    def auth():
        """HTTP basic auth (user: admin) once a password is stored in /config/web-password.
        Without one (the provisioning card) the UI is open: the card is in your hand."""
        if not password_set() or request.path.startswith("/static/"):
            return None
        a = request.authorization
        if a and a.type == "basic" and password_ok(a.password or ""):
            return None
        return Response("login required", 401, {"WWW-Authenticate": 'Basic realm="Antminer I/O module"'})

    @app.context_processor
    def inject():
        return {"version": __version__, "busy": runner.busy(), "current_job": runner.current,
                "password_set": password_set()}

    # ---- board ------------------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html", b=board.identity(), mtd=board.mtd_table(),
                               sd=board.sd_card(), data=board.data_status())

    @app.route("/api/status")
    def api_status():
        return jsonify(board.identity())

    # ---- NAND -------------------------------------------------------------------------
    @app.route("/nand")
    def nand():
        payload = board.payload_files()
        dtbs = [dict(f, profile=board.dtb_profile(os.path.join(board.PAYLOAD_DIR, f["name"]))) for f in payload if f["kind"] == "dtb"]
        kernels = [f for f in payload if f["kind"] == "kernel"]
        initrds = [f for f in payload if f["kind"] == "initramfs"]
        contents = board.nand_contents() if request.args.get("scan") else None
        return render_template("nand.html", payload=payload, dtbs=dtbs, kernels=kernels, initrds=initrds,
                               contents=contents, payload_dir=board.PAYLOAD_DIR, data=board.data_status(),
                               root=board.identity()["root"])

    @app.route("/nand/flash", methods=["POST"])
    def nand_flash():
        kernel, dtb, initrd = request.form.get("kernel"), request.form.get("dtb"), request.form.get("initrd")
        for f in (kernel, dtb, initrd):
            if not f or "/" in f or not os.path.exists(os.path.join(board.PAYLOAD_DIR, f)):
                abort(400, "bad payload file")
        args = ["sh", FLASH]
        if request.form.get("wipe_config"):
            args.append("--wipe-config")
        args += [board.PAYLOAD_DIR, kernel, dtb, initrd]
        return _start("Flash NAND (mtd6/7/8)", args)

    @app.route("/nand/dtb-only", methods=["POST"])
    def nand_dtb_only():
        dtb = request.form.get("dtb", "")
        if "/" in dtb or not os.path.exists(os.path.join(board.PAYLOAD_DIR, dtb)):
            abort(400, "bad dtb")
        return _start(f"Write {dtb} to mtd6", ["sh", FLASH, "--dtb-only", board.PAYLOAD_DIR, dtb])

    @app.route("/nand/data/<action>", methods=["POST"])
    def nand_data(action):
        if action not in ("init", "enable", "disable", "wipe"):
            abort(400)
        return _start(f"antminer-data {action}", ["antminer-data", action])

    @app.route("/reboot", methods=["POST"])
    def reboot():
        subprocess.Popen(["sh", "-c", "sleep 2; reboot"])
        return render_template("message.html", title="Rebooting", text="The board reboots in 2 seconds. "
                               "Remove the SD card now if it should boot from NAND.")

    # ---- pinmux -----------------------------------------------------------------------
    @app.route("/pinmux")
    def pinmux():
        return render_template("pinmux.html", profiles=board.profiles(), current=board.identity()["profile"])

    @app.route("/pinmux/pads")
    def pinmux_pads():
        return render_template("pads.html", rows=_pad_rows())

    @app.route("/pinmux/<name>", methods=["GET", "POST"])
    def pinmux_edit(name):
        if not SAFE_NAME.match(name):
            abort(400)
        local = os.path.join(board.CONFIG_DIR, "pinmux", f"{name}.yaml")
        shipped = os.path.join(board.PINMUX_DIR, "boards", f"{name}.yaml")
        path = local if os.path.exists(local) else shipped
        result = None
        text = request.form.get("yaml") if request.method == "POST" else None
        if request.method == "POST":
            action = request.form.get("action")
            if action in ("save", "flash"):
                os.makedirs(os.path.dirname(local), exist_ok=True)
                with open(local, "w", newline="\n") as fh:
                    fh.write(text.replace("\r\n", "\n"))
                path = local
            tmp = "/tmp/antminer-web-check.yaml"
            with open(tmp, "w", newline="\n") as fh:
                fh.write(text.replace("\r\n", "\n"))
            rc, out = run_quick([DTB, "build", tmp, f"/tmp/am335x-antminer-{name}.dtb"])
            pinmap = ""
            if rc == 0:
                dts = board.read(f"/tmp/am335x-antminer-{name}.dts")
                m = re.search(r"/\*\n \* Pin map:(.*?)\*/", dts, re.S)
                pinmap = m.group(1) if m else ""
                size = os.path.getsize(f"/tmp/am335x-antminer-{name}.dtb")
                out = (out + f"\nDTB: {size} bytes").strip()
            result = {"rc": rc, "out": out, "pinmap": pinmap, "saved": action in ("save", "flash")}
            if rc == 0 and action == "flash":
                return _start(f"pinmux profile '{name}' -> mtd6", [DTB, "flash", f"/tmp/am335x-antminer-{name}.dtb"])
        else:
            text = board.read(path) if os.path.exists(path) else f"name: {name}\n\npins:\n\nadc: []\n"
        return render_template("pinmux_edit.html", name=name, text=text, result=result,
                               origin="local" if path == local else ("shipped" if os.path.exists(shipped) else "new"),
                               pads=[r for r in _pad_rows() if r["state"] == "free"], current=_current_pins(text))

    # ---- board editor (Lit component + JSON API) ----------------------------------------
    @app.route("/pinmux/<name>/board")
    def pinmux_board(name):
        if not SAFE_NAME.match(name):
            abort(400)
        return render_template("board.html", name=name, current=board.identity()["profile"])

    @app.route("/api/pads")
    def api_pads():
        return jsonify({"pads": _pad_rows(), "headers": _header_layout()})

    @app.route("/api/profiles")
    def api_profiles():
        return jsonify(board.profiles())

    @app.route("/api/profiles/<name>", methods=["GET", "PUT"])
    def api_profile(name):
        if not SAFE_NAME.match(name):
            abort(400)
        local = os.path.join(board.CONFIG_DIR, "pinmux", f"{name}.yaml")
        shipped = os.path.join(board.PINMUX_DIR, "boards", f"{name}.yaml")
        if request.method == "PUT":
            model = request.get_json(force=True, silent=True)
            if not isinstance(model, dict):
                abort(400, "JSON model expected")
            model["name"] = name
            text = profile.dump(model)
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "w", newline="\n") as fh:
                fh.write(text)
            run_quick(["sync"])
            return jsonify({"saved": local, "yaml": text})
        path = local if os.path.exists(local) else shipped
        text = board.read(path) if os.path.exists(path) else f"name: {name}\npins: {{}}\nadc: []\n"
        try:
            model = profile.load(text)
        except Exception as ex:  # noqa: BLE001
            return jsonify({"error": f"cannot parse profile: {ex}"}), 422
        model["origin"] = "local" if path == local else ("shipped" if os.path.exists(shipped) else "new")
        model["yaml"] = text
        return jsonify(model)

    @app.route("/api/profiles/<name>/yaml", methods=["POST"])
    def api_profile_yaml(name):
        model = request.get_json(force=True, silent=True) or {}
        model["name"] = name
        return Response(profile.dump(model), mimetype="text/plain")

    @app.route("/api/profiles/<name>/build", methods=["POST"])
    def api_profile_build(name):
        """validate + compile a JSON model on the board; returns per-pin errors and the pin map"""
        if not SAFE_NAME.match(name):
            abort(400)
        model = request.get_json(force=True, silent=True) or {}
        model["name"] = name
        tmp = f"/tmp/antminer-web-{name}.yaml"
        with open(tmp, "w", newline="\n") as fh:
            fh.write(profile.dump(model))
        dtb = f"/tmp/am335x-antminer-{name}.dtb"
        rc, out = run_quick([DTB, "build", tmp, dtb], timeout=120)
        result = {"ok": rc == 0, "output": out.strip(), "dtb_size": os.path.getsize(dtb) if rc == 0 and os.path.exists(dtb) else None}
        js = dtb[:-4] + ".json"
        if os.path.exists(js):
            with open(js) as fh:
                result.update(json.load(fh))
        if not result.get("errors") and rc != 0:
            result["errors"] = [{"pin": None, "text": out.strip()[-500:]}]
        return jsonify(result)

    @app.route("/api/profiles/<name>/flash", methods=["POST"])
    def api_profile_flash(name):
        if not SAFE_NAME.match(name):
            abort(400)
        dtb = f"/tmp/am335x-antminer-{name}.dtb"
        if not os.path.exists(dtb):
            return jsonify({"error": "build first"}), 409
        try:
            j = runner.start(f"pinmux profile '{name}' -> mtd6", [DTB, "flash", dtb])
        except RuntimeError as ex:
            return jsonify({"error": str(ex)}), 409
        return jsonify({"job": j.id, "url": url_for("job", job_id=j.id)})

    # ---- services ---------------------------------------------------------------------
    @app.route("/services", methods=["GET", "POST"])
    def services():
        msg = None
        if request.method == "POST":
            cfg = board.CONFIG_DIR
            os.makedirs(os.path.join(cfg, "ssh"), exist_ok=True)
            _write_or_remove(os.path.join(cfg, "hostname"), re.sub(r"[^A-Za-z0-9-]", "", request.form.get("hostname", "")))
            _write_or_remove(os.path.join(cfg, "ntp-server"), re.sub(r"[^A-Za-z0-9.:-]", "", request.form.get("ntp", "")))
            mode = request.form.get("mode", "dhcp")
            if mode == "static":
                net = "\n".join(f'{k}="{re.sub(r"[^0-9. ]", "", request.form.get(k.lower(), ""))}"'
                                for k in ("ADDRESS", "NETMASK", "GATEWAY", "DNS"))
                _write_or_remove(os.path.join(cfg, "network"), f'MODE="static"\n{net}\n')
            else:
                _write_or_remove(os.path.join(cfg, "network"), "")
            _write_or_remove(os.path.join(cfg, "ssh", "authorized_keys"), request.form.get("authorized_keys", "").replace("\r\n", "\n"))
            pw = request.form.get("web_password", "")
            if request.form.get("web_password_clear"):
                _write_or_remove(PASSWORD_FILE, "")
            elif pw:
                password_store(pw)
            run_quick(["sync"])
            msg = "Saved to /config. Hostname and network apply at the next boot (or: /etc/init.d/antminer-config start)."
        return render_template("services.html", c=board.config_values(), msg=msg)

    # ---- log / jobs -------------------------------------------------------------------
    @app.route("/log")
    def log():
        rc, dmesg = run_quick(["sh", "-c", "dmesg | tail -n 120"])
        return render_template("log.html", dmesg=dmesg, jobs=list(reversed(runner.history)))

    @app.route("/job/<int:job_id>")
    def job(job_id):
        j = runner.get(job_id)
        if not j:
            abort(404)
        return render_template("job.html", job=j)

    @app.route("/api/job/<int:job_id>")
    def api_job(job_id):
        j = runner.get(job_id)
        if not j:
            abort(404)
        return jsonify(j.as_dict())

    def _start(title, cmd):
        try:
            j = runner.start(title, cmd)
        except RuntimeError as ex:
            return render_template("message.html", title="Busy", text=str(ex)), 409
        return redirect(url_for("job", job_id=j.id))

    return app


def _write_or_remove(path, text):
    text = text.strip()
    if text:
        with open(path, "w", newline="\n") as fh:
            fh.write(text + "\n")
    elif os.path.exists(path):
        os.unlink(path)


# functions the generator knows how to wire up (periph_of in gen-dts.py) + plain gpio
FUNC_RE = re.compile(r"^(uart\d_(rxd|txd|ctsn|rtsn)|i2c\d_(sda|scl)|spi\d_(sclk|d0|d1|cs\d)|ehrpwm\d[ab]|"
                     r"ecap\d_in_pwm\d_out|dcan\d_(rx|tx)|eqep\d\w*|timer\d)$")


def _pad_rows():
    """P8/P9 table: pad, modes, gpio, reserved reason (from gen-dts.py's RESERVED map)"""
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location("gen_dts", os.path.join(board.PINMUX_DIR, "gen-dts.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    with open(os.path.join(board.PINMUX_DIR, "am335x-bbb-pins.json")) as fh:
        db = json.load(fh)
    rows = []
    for pin, e in db.items():
        off = e.get("offset")
        if off is None:
            rows.append({"pin": pin, "name": e.get("name"), "modes": "", "gpio": "", "state": "power", "funcs": []})
            continue
        offv = int(off, 16) if isinstance(off, str) else off
        why = g.RESERVED.get(offv) if isinstance(g.RESERVED, dict) else ("reserved" if offv in g.RESERVED else None)
        all_modes = [m for m in (e.get("modes") or []) if m]
        funcs = [m for m in all_modes if FUNC_RE.match(m)]
        if any(m.startswith("gpio") for m in all_modes):
            funcs.append("gpio")
        rows.append({"pin": pin, "name": e.get("name"), "pad": f"0x{offv:03x}", "modes": ", ".join(all_modes),
                     "gpio": e.get("gpio") or "", "state": why or "free", "funcs": funcs})
    rows.sort(key=lambda r: (r["pin"].split(".")[0], int(r["pin"].split(".")[1])))
    return rows


def _header_layout():
    """P9 / P8 as the physical 2x23 headers: rows of (odd pin, even pin), pin 1 at the top.
    Power pins carry their rail name so the editor can draw them."""
    import json
    with open(os.path.join(board.PINMUX_DIR, "am335x-bbb-pins.json")) as fh:
        db = json.load(fh)
    layout = {}
    for hdr in ("P9", "P8"):
        rows = []
        for n in range(1, 47, 2):
            row = []
            for pin in (f"{hdr}.{n}", f"{hdr}.{n + 1}"):
                e = db.get(pin, {})
                row.append({"pin": pin, "name": e.get("name", ""), "power": e.get("offset") is None})
            rows.append(row)
        layout[hdr] = rows
    return layout


def _current_pins(text):
    """pins: section of a profile -> {pin: {func, dir, pull, init, name, hog}} for the table"""
    try:
        import yaml
        doc = yaml.safe_load(text) or {}
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for pin, spec in (doc.get("pins") or {}).items():
        if isinstance(spec, str):
            spec = {"func": spec}
        if not isinstance(spec, dict):
            continue
        out[str(pin)] = {"func": str(spec.get("func", "")), "dir": str(spec.get("dir", "in")),
                         "pull": str(spec.get("pull", "")), "init": str(spec.get("init", "0")),
                         "name": str(spec.get("name", "")), "hog": bool(spec.get("hog", False))}
    return out
