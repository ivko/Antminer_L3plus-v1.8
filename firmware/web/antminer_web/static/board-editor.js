// <antminer-board profile="name">: visual pinmux editor. Lit (vendored lit-all.min.js), no build step.
// Talks to the JSON API of the Flask app: /api/pads, /api/profiles/<name>[/build|/flash|/yaml].
import { LitElement, html, css, nothing } from "./lit-all.min.js";

const CATEGORY_OF = [
  [/^uart/, "uart"], [/^i2c/, "i2c"], [/^spi/, "spi"], [/^(ehrpwm|ecap)/, "pwm"],
  [/^dcan/, "can"], [/^(timer|eqep)/, "timer"],
];
function category(spec) {
  if (!spec) return "free";
  if (spec.func === "gpio") return spec.dir === "out" ? "gpio_out" : "gpio_in";
  for (const [re, c] of CATEGORY_OF) if (re.test(spec.func)) return c;
  return "other";
}
const ICON = { power: "⏚", reserved: "🔒", free: "", gpio_in: "⇥", gpio_out: "⇤", uart: "⇄", i2c: "I²C", spi: "SPI",
               pwm: "∿", can: "CAN", timer: "⏱", adc: "∿", other: "·" };
const RAIL = { GND: "gnd", "DC_3.3V": "v33", VDD_5V: "v5", SYS_5V: "v5", VADC: "vadc", AGND: "gnd" };
const ADC_PINS = { "P9.39": 0, "P9.40": 1, "P9.37": 2, "P9.38": 3, "P9.33": 4, "P9.36": 5, "P9.35": 6 };
// the partner pins a peripheral function normally needs (uart rx+tx, i2c sda+scl, spi sclk+d0+d1)
function partners(func) {
  let m;
  if ((m = func.match(/^(uart\d)_(rxd|txd)$/))) return [`${m[1]}_rxd`, `${m[1]}_txd`].filter(f => f !== func);
  if ((m = func.match(/^(i2c\d)_(sda|scl)$/))) return [`${m[1]}_sda`, `${m[1]}_scl`].filter(f => f !== func);
  if ((m = func.match(/^(spi\d)_(sclk|d0|d1|cs\d)$/))) return [`${m[1]}_sclk`, `${m[1]}_d0`, `${m[1]}_d1`].filter(f => f !== func);
  if ((m = func.match(/^(dcan\d)_(rx|tx)$/))) return [`${m[1]}_rx`, `${m[1]}_tx`].filter(f => f !== func);
  return [];
}
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
// I2C devices whose drivers are built into the image's kernel (gpio-pcf857x, hwmon lm75)
const I2C_KNOWN = [
  { c: "nxp,pcf8574", label: "PCF8574 8-bit GPIO expander", addr: 0x20, gpio: 8, hint: "address 0x20..0x27 (A0-A2)" },
  { c: "nxp,pcf8574a", label: "PCF8574A 8-bit GPIO expander", addr: 0x38, gpio: 8, hint: "address 0x38..0x3f (A0-A2)" },
  { c: "nxp,pcf8575", label: "PCF8575 16-bit GPIO expander", addr: 0x20, gpio: 16, hint: "address 0x20..0x27" },
  { c: "ti,tmp1075", label: "TMP1075 temperature sensor", addr: 0x48, hint: "hwmon (lm75 driver), 0x48..0x4f" },
  { c: "ti,tmp102", label: "TMP102 temperature sensor", addr: 0x48, hint: "needs CONFIG_SENSORS_TMP102 (not in the image)" },
  { c: "national,lm75", label: "LM75 temperature sensor", addr: 0x48, hint: "hwmon (lm75 driver)" },
  { c: "national,lm75b", label: "LM75B temperature sensor", addr: 0x48, hint: "hwmon (lm75 driver)" },
  { c: "ti,tmp75", label: "TMP75 temperature sensor", addr: 0x48, hint: "hwmon (lm75 driver)" },
];

class AntminerBoard extends LitElement {
  static properties = {
    profile: { type: String },
    pads: { state: true }, headers: { state: true }, model: { state: true }, original: { state: true },
    sel: { state: true }, draft: { state: true }, result: { state: true }, busy: { state: true }, msg: { state: true },
    newPad: { state: true },
  };

  static styles = css`
    :host { display: block; --gnd:#7a7f87; --v33:#d9534f; --v5:#e8872c; --vadc:#c2185b;
            --free:#ffffff; --reserved:#e3e6ea; --gpio_in:#3b82f6; --gpio_out:#16a34a; --uart:#7c3aed; --i2c:#0d9488;
            --spi:#4f46e5; --pwm:#d97706; --can:#92400e; --timer:#65a30d; --adc:#db2777; --other:#64748b;
            --line:#d9dde2; --mute:#5b6270; --err:#b3261e; --warn:#9a6700; --acc:#0b63c6; font-size: 15px; }
    .bar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin: 6px 0 12px; }
    button { padding: 7px 14px; border:1px solid var(--acc); background:var(--acc); color:#fff; border-radius:4px; cursor:pointer; font-size:14px; }
    button.sec { background:#fff; color:var(--acc); } button.danger { background:var(--err); border-color:var(--err); }
    button[disabled] { opacity:.5; cursor:not-allowed; }
    .msg { color: var(--mute); } .msg.err { color: var(--err); } .msg.ok { color: var(--gpio_out); }
    .layout { display:grid; grid-template-columns: 360px minmax(320px, 1fr) 360px; gap: 18px; align-items:start; }
    .hdr { background:#20242a; border-radius: 8px; padding: 8px 6px; }
    .hdr h3 { color:#fff; margin: 0 0 8px; text-align:center; font-size: 17px; letter-spacing: .08em; }
    .row { display:grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 5px; }
    .tile { position:relative; min-height: 52px; border-radius: 5px; padding: 4px 30px 4px 8px; background: var(--free);
            border: 2px solid transparent; cursor:pointer; color:#1d2126; overflow:hidden; line-height:1.25; }
    .tile .n { position:absolute; top:3px; right:5px; font-size: 13px; font-weight: 700; color:#333; }
    .tile.power .n, .tile.gpio_in .n, .tile.gpio_out .n, .tile.uart .n, .tile.i2c .n, .tile.spi .n, .tile.pwm .n,
    .tile.can .n, .tile.timer .n, .tile.adc .n, .tile.other .n { color:#fff; opacity:.9; }
    .tile .name { font-weight: 700; font-size: 15px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .tile .sub { font-size: 12.5px; opacity: .92; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .tile .ic { position:absolute; bottom:3px; right:6px; font-size: 17px; opacity:.9; }
    .extra { display:grid; grid-template-columns: 1fr 1fr; gap: 5px; }
    .tile.power { color:#fff; cursor:default; } .tile.gnd { background:var(--gnd);} .tile.v33 { background:var(--v33);} .tile.v5 { background:var(--v5);} .tile.vadc { background:var(--vadc);}
    .tile.reserved { background: repeating-linear-gradient(45deg, var(--reserved), var(--reserved) 4px, #f4f5f7 4px, #f4f5f7 8px); color:#777; cursor: not-allowed; }
    .tile.gpio_in, .tile.gpio_out, .tile.uart, .tile.i2c, .tile.spi, .tile.pwm, .tile.can, .tile.timer, .tile.adc, .tile.other { color:#fff; }
    .tile.gpio_in { background: var(--gpio_in);} .tile.gpio_out { background: var(--gpio_out);} .tile.uart { background: var(--uart);}
    .tile.i2c { background: var(--i2c);} .tile.spi { background: var(--spi);} .tile.pwm { background: var(--pwm);} .tile.can { background: var(--can);}
    .tile.timer { background: var(--timer);} .tile.adc { background: var(--adc);} .tile.other { background: var(--other);}
    .tile.free:hover { border-color: var(--acc); }
    .tile.mod { border-color: #ffd54f; box-shadow: 0 0 0 1px #ffd54f inset; }
    .tile.mod::before { content:""; position:absolute; left:2px; top:2px; width:6px; height:6px; border-radius:50%; background:#ffd54f; }
    .tile.bad { border-color: var(--err); box-shadow: 0 0 0 1px var(--err) inset; }
    .tile.partial { border-color: var(--warn); }
    .tile.hog .name::after { content:" 🔒"; font-size: 12px; }
    .mid { display:flex; flex-direction:column; gap: 12px; }
    .card { background:#fff; border:1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
    .card h4 { margin: 0 0 8px; font-size: 16px; }
    .legend { display:flex; flex-wrap:wrap; gap: 8px 12px; } .legend span { display:inline-flex; align-items:center; gap:5px; font-size: 14px; }
    .legend i { width: 15px; height: 15px; border-radius: 3px; display:inline-block; border:1px solid #0002; }
    .adc { display:flex; gap: 6px; flex-wrap:wrap; } .adc label { display:inline-flex; gap:4px; align-items:center; padding: 4px 10px; border:1px solid var(--line); border-radius: 4px; cursor:pointer; font-size: 14px; }
    .adc label.on { background: var(--adc); color:#fff; border-color: var(--adc); }
    table { border-collapse: collapse; width: 100%; } td, th { text-align:left; padding: 4px 6px; border-bottom:1px solid var(--line); font-size: 14px; }
    .err { color: var(--err); } .warn { color: var(--warn); } .hint { color: var(--mute); font-size: 13px; }
    dialog { border: 1px solid var(--line); border-radius: 8px; padding: 18px 20px; width: 500px; max-width: 95vw; font-size: 15px; }
    dialog::backdrop { background: rgba(0,0,0,.35); }
    dialog h3 { margin: 0 0 2px; font-size: 19px; } dialog .meta { color: var(--mute); font-size: 13px; margin-bottom: 10px; }
    dialog label { display:block; margin: 9px 0 4px; font-weight: 500; }
    dialog select, dialog input[type=text], .card select, .card input[type=text] { width:100%; padding: 6px 8px; border:1px solid var(--line); border-radius:4px; font-size: 15px; box-sizing: border-box; }
    .inline { display:flex; gap: 12px; flex-wrap: wrap; align-items: center; } .inline label { font-weight: normal; margin: 4px 0; }
    .actions { display:flex; gap: 8px; justify-content:flex-end; margin-top: 16px; }
    .partners { font-size: 14px; color: var(--mute); margin-top: 6px; }
    .partners b { color: var(--warn); }
    pre { background:#f6f7f8; border:1px solid var(--line); padding:8px; font: 13px/1.4 ui-monospace, Consolas, monospace; max-height: 220px; overflow:auto; white-space: pre-wrap; }
    .dev { border:1px solid var(--line); border-radius: 5px; padding: 8px 10px; margin: 8px 0; }
    .dev .grid { display:grid; grid-template-columns: 2fr 1fr 1fr; gap: 8px; }
    .dev .grid label { font-size: 13px; color: var(--mute); display:block; margin-bottom: 2px; }
    .dev .head { display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px; font-weight:600; }
    button.small { padding: 3px 9px; font-size: 13px; }
  `;

  constructor() {
    super();
    this.pads = []; this.headers = {}; this.model = null; this.original = null; this.sel = null; this.draft = null;
    this.result = null; this.busy = false; this.msg = ""; this.newPad = "";
  }

  connectedCallback() { super.connectedCallback(); this.load(); }

  async load() {
    try {
      const [p, m] = await Promise.all([fetch("/api/pads").then(r => r.json()), fetch(`/api/profiles/${this.profile}`).then(r => r.json())]);
      this.pads = p.pads; this.headers = p.headers;
      if (m.error) { this.msg = m.error; return; }
      this.model = m; this.original = JSON.parse(JSON.stringify(m));
      this.msg = `${m.origin} profile, ${Object.keys(m.pins).length} pins configured`;
      const open = new URLSearchParams(location.search).get("open");   // deep link: ?open=P8.43
      if (open) this.updateComplete.then(() => this.open(open));
    } catch (e) { this.msg = "load failed: " + e; }
  }

  // ---- model helpers --------------------------------------------------------------------
  pad(pin) { return this.pads.find(p => p.pin === pin); }
  spec(pin) { return this.model?.pins?.[pin]; }
  modified(pin) { return !same(this.model?.pins?.[pin], this.original?.pins?.[pin]); }
  changes() {
    if (!this.model) return 0;
    const keys = new Set([...Object.keys(this.model.pins), ...Object.keys(this.original.pins)]);
    let n = 0; for (const k of keys) if (this.modified(k)) n++;
    if (!same(this.model.adc, this.original.adc)) n++;
    if (!same(this.model.i2c, this.original.i2c)) n++;
    return n;
  }
  funcsInUse() { const s = new Set(); for (const p of Object.values(this.model?.pins ?? {})) s.add(p.func); return s; }
  partial(spec) { if (!spec || spec.func === "gpio") return false; const used = this.funcsInUse(); return partners(spec.func).some(f => !used.has(f)); }
  errorsFor(pin) { return (this.result?.errors ?? []).filter(e => e.pin === pin); }
  names() { const m = {}; for (const [k, p] of Object.entries(this.model?.pins ?? {})) if (p.func === "gpio" && p.name) (m[p.name] ??= []).push(k); return m; }

  setPin(pin, spec) {
    const pins = { ...this.model.pins };
    if (spec) pins[pin] = spec; else delete pins[pin];
    this.model = { ...this.model, pins };
    this.result = null;
  }
  toggleAdc(ch) {
    const adc = new Set(this.model.adc);
    adc.has(ch) ? adc.delete(ch) : adc.add(ch);
    this.model = { ...this.model, adc: [...adc].sort((a, b) => a - b) };
    this.result = null;
  }
  undoAll() { this.model = JSON.parse(JSON.stringify(this.original)); this.result = null; this.msg = "changes discarded"; }

  // ---- dialog ---------------------------------------------------------------------------
  open(pin) {
    const pad = this.pad(pin);
    if (pad && (pad.state === "power" || (pad.state !== "free"))) return;
    const s = this.spec(pin);
    this.sel = pin;
    this.draft = s ? { ...s } : { func: "", dir: "in", init: 0, pull: "", name: "", hog: false, comment: "" };
    this.updateComplete.then(() => this.renderRoot.querySelector("dialog")?.showModal());
  }
  close() { this.renderRoot.querySelector("dialog")?.close(); this.sel = null; }
  apply() {
    const d = this.draft, pin = this.sel;
    if (!d.func) { this.setPin(pin, null); this.close(); return; }
    const spec = { func: d.func };
    if (d.func === "gpio") {
      spec.dir = d.dir || "in";
      if (spec.dir === "out") spec.init = Number(d.init) ? 1 : 0;
      if (d.pull) spec.pull = d.pull;
      if (d.name?.trim()) spec.name = d.name.trim();
      if (d.hog) spec.hog = true;
    } else if (d.pull) spec.pull = d.pull;
    if (d.comment?.trim()) spec.comment = d.comment.trim();
    this.setPin(pin, spec);
    this.close();
  }
  clearPin() { this.setPin(this.sel, null); this.close(); }

  // ---- server actions -------------------------------------------------------------------
  async post(url, body) {
    const r = await fetch(url, { method: body === undefined ? "POST" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
    return r.json();
  }
  async validate() {
    this.busy = true; this.msg = "building on the board...";
    try {
      this.result = await this.post(`/api/profiles/${this.profile}/build`, this.model);
      this.msg = this.result.ok ? `OK: DTB ${this.result.dtb_size} bytes, ${this.result.pins?.length ?? "?"} pads, peripherals: ${(this.result.peripherals ?? []).join(", ") || "-"}`
                                : `${this.result.errors?.length ?? 1} error(s)`;
    } catch (e) { this.msg = "build failed: " + e; }
    this.busy = false;
  }
  async save() {
    this.busy = true;
    try {
      const r = await fetch(`/api/profiles/${this.profile}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.model) });
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      this.original = JSON.parse(JSON.stringify(this.model)); this.model = { ...this.model, origin: "local" };
      this.msg = `saved to ${j.saved}`;
    } catch (e) { this.msg = "save failed: " + e; }
    this.busy = false;
  }
  async flash() {
    if (!this.result?.ok) { await this.validate(); if (!this.result?.ok) return; }
    if (!confirm(`Save profile '${this.profile}' and write it to NAND mtd6? Takes effect at the next boot.`)) return;
    await this.save();
    const j = await this.post(`/api/profiles/${this.profile}/flash`);
    if (j.url) location.href = j.url; else this.msg = j.error || "flash failed";
  }
  async exportYaml() {
    const r = await fetch(`/api/profiles/${this.profile}/yaml`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.model) });
    const blob = await r.blob(); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `${this.profile}.yaml`; a.click();
  }

  // ---- rendering ------------------------------------------------------------------------
  tile(cell) {
    const pin = cell.pin, pad = this.pad(pin), spec = this.spec(pin);
    const adcCh = ADC_PINS[pin];
    if (adcCh !== undefined) {            // analog inputs have no pad register: before the power check
      const on = this.model?.adc?.includes(adcCh);
      return html`<div class="tile ${on ? "adc" : "free"} ${!same(on, this.original?.adc?.includes(adcCh)) ? "mod" : ""}" title="AIN${adcCh} 1.8 V analog input" @click=${() => this.toggleAdc(adcCh)}>
        <span class="n">${pin.includes(".") ? pin.split(".")[1] : ""}</span><div class="name">AIN${adcCh}</div><div class="sub">${on ? "enabled" : "analog, off"}</div><span class="ic">${ICON.adc}</span></div>`;
    }
    if (cell.power) {
      const rail = RAIL[cell.name] || "gnd";
      return html`<div class="tile power ${rail}" title="${cell.name}"><span class="n">${pin.includes(".") ? pin.split(".")[1] : ""}</span><div class="name">${cell.name}</div><span class="ic">${ICON.power}</span></div>`;
    }
    if (pad && pad.state !== "free") {
      return html`<div class="tile reserved" title="${pin} ${pad.pad}: reserved for ${pad.state}"><span class="n">${pin.includes(".") ? pin.split(".")[1] : ""}</span><div class="name">${pad.name}</div><div class="sub">${pad.state}</div><span class="ic">${ICON.reserved}</span></div>`;
    }
    const cat = category(spec);
    const cls = [cat, this.modified(pin) ? "mod" : "", this.errorsFor(pin).length ? "bad" : "", this.partial(spec) ? "partial" : "", spec?.hog ? "hog" : ""].join(" ");
    const title = `${pin} · ${pad?.pad ?? ""} · ${pad?.gpio ? "gpio" + pad.gpio.join("_") : ""}` + (spec?.comment ? `\n${spec.comment}` : "") + (this.errorsFor(pin).map(e => "\n! " + e.text).join(""));
    const name = spec ? (spec.func === "gpio" ? (spec.name || "gpio") : spec.func) : (pad?.name ?? "");
    const sub = spec ? (spec.func === "gpio" ? `${spec.dir === "out" ? "out, init " + (spec.init ?? 0) : "in"}${spec.pull ? ", pull " + spec.pull : ""}` : "") : (pad?.gpio ? "gpio" + pad.gpio.join("_") : "");
    return html`<div class="tile ${cls}" title="${title}" @click=${() => this.open(pin)}>
      <span class="n">${pin.includes(".") ? pin.split(".")[1] : ""}</span><div class="name">${name}</div><div class="sub">${sub}</div><span class="ic">${ICON[cat] ?? ""}</span></div>`;
  }

  header(hdr) {
    const rows = this.headers[hdr] ?? [];
    return html`<div class="hdr"><h3>${hdr}</h3>${rows.map(r => html`<div class="row">${this.tile(r[0])}${this.tile(r[1])}</div>`)}</div>`;
  }

  extraPads() {
    const rows = this.pads.filter(p => p.extra);
    const unknown = Object.keys(this.model?.pins ?? {}).filter(k => !/^P[89]\./.test(k) && !rows.some(r => r.pin === k));
    return html`<div class="card"><h4>Pads outside the headers (Bitmain connectors)</h4>
      <div class="extra">${rows.map(r => this.tile({ pin: r.pin, name: r.name, power: false }))}</div>
      ${unknown.length ? html`<table style="margin-top:8px">${unknown.map(k => { const s = this.spec(k); return html`<tr><td>${k}</td>
        <td>${s.func === "gpio" ? (s.name || "gpio") + " " + (s.dir || "in") : s.func}</td><td><button class="sec small" @click=${() => this.open(k)}>edit</button></td></tr>`; })}</table>` : nothing}
      <div class="inline" style="margin-top:8px"><input type="text" placeholder="other pad by name, e.g. gpmc_a5" .value=${this.newPad} @input=${e => this.newPad = e.target.value} style="flex:1">
        <button class="sec small" ?disabled=${!this.newPad.trim()} @click=${() => { this.open(this.newPad.trim()); this.newPad = ""; }}>add</button></div></div>`;
  }

  // ---- I2C devices ----------------------------------------------------------------------
  i2cBuses() {
    const s = new Set(Object.keys(this.model?.i2c ?? {}));
    for (const p of Object.values(this.model?.pins ?? {})) { const m = String(p.func).match(/^(i2c\d)_(sda|scl)$/); if (m) s.add(m[1]); }
    return [...s].sort();
  }
  busPins(bus) { const f = new Set(Object.values(this.model.pins).map(p => p.func)); return f.has(`${bus}_sda`) && f.has(`${bus}_scl`); }
  setI2c(bus, cfg) { this.model = { ...this.model, i2c: { ...(this.model.i2c ?? {}), [bus]: cfg } }; this.result = null; }
  addDevice(bus) {
    const cfg = this.model.i2c?.[bus] ?? { "clock-frequency": 100000 };
    const c = this.renderRoot.querySelector(`#add-${bus}`)?.value ?? "";
    const k = I2C_KNOWN.find(x => x.c === c);
    const used = new Set((cfg.devices ?? []).map(d => Number(d.reg)));
    let reg = k?.addr ?? 0x20; while (used.has(reg) && reg < 0x77) reg++;
    const dev = { compatible: c || "vendor,device", reg };
    if (k?.gpio) dev.props = { "gpio-controller": true, "#gpio-cells": 2, "gpio-line-names": Array.from({ length: k.gpio }, (_, i) => `EXP${i}`) };
    this.setI2c(bus, { ...cfg, devices: [...(cfg.devices ?? []), dev] });
  }
  i2cDev(bus, cfg, d, i, regs) {
    const k = I2C_KNOWN.find(x => x.c === d.compatible);
    const reg = Number(d.reg);
    const bad = !(reg >= 0x03 && reg <= 0x77) ? "address must be 0x03..0x77"
              : regs.filter(r => r === reg).length > 1 ? "address used twice on this bus" : "";
    const upd = (patch) => { const devs = [...cfg.devices]; devs[i] = { ...d, ...patch }; this.setI2c(bus, { ...cfg, devices: devs }); };
    const isGpio = k?.gpio || d.props?.["gpio-controller"];
    const names = (d.props?.["gpio-line-names"] ?? []).join(", ");
    return html`<div class="dev">
      <div class="head"><span>${k ? k.label : d.compatible}</span>
        <button class="danger small" @click=${() => this.setI2c(bus, { ...cfg, devices: cfg.devices.filter((_, j) => j !== i) })}>remove</button></div>
      <div class="grid">
        <div><label>compatible</label><input type="text" .value=${d.compatible} @change=${e => upd({ compatible: e.target.value.trim() })}></div>
        <div><label>address</label><input type="text" .value=${"0x" + reg.toString(16)} @change=${e => upd({ reg: parseInt(e.target.value, 16) || 0 })}></div>
        <div><label>label</label><input type="text" .value=${d.label ?? ""} @change=${e => upd({ label: e.target.value.trim() || undefined })}></div>
      </div>
      ${isGpio ? html`<label style="font-size:13px;color:var(--mute);display:block;margin:6px 0 2px">GPIO line names (${k?.gpio ?? "?"} lines, comma separated, visible in gpioinfo)</label>
        <input type="text" .value=${names} @change=${e => upd({ props: { ...(d.props ?? {}), "gpio-controller": true, "#gpio-cells": 2,
          "gpio-line-names": e.target.value.split(",").map(s => s.trim()).filter(Boolean) } })}>` : nothing}
      ${k?.hint ? html`<div class="hint">${k.hint}</div>` : nothing}
      ${bad ? html`<div class="err">${bad}</div>` : nothing}
    </div>`;
  }
  i2cCard() {
    const buses = this.i2cBuses();
    if (!buses.length) return html`<div class="card"><h4>I2C devices</h4><p class="hint">No I2C bus enabled. Give two pins the functions i2cN_sda and i2cN_scl, then add devices here.</p></div>`;
    return html`<div class="card"><h4>I2C devices</h4>${buses.map(bus => {
      const cfg = this.model.i2c?.[bus] ?? {};
      const devs = cfg.devices ?? [];
      const regs = devs.map(d => Number(d.reg));
      return html`<div style="margin-bottom:10px">
        <div class="inline"><b>${bus}</b>
          <select style="width:auto" @change=${e => this.setI2c(bus, { ...cfg, "clock-frequency": Number(e.target.value) })}>
            ${[100000, 400000].map(f => html`<option value=${f} ?selected=${Number(cfg["clock-frequency"] ?? 100000) === f}>${f / 1000} kHz</option>`)}
          </select>
          ${this.busPins(bus) ? nothing : html`<span class="warn">SDA/SCL pins not both configured</span>`}</div>
        ${devs.map((d, i) => this.i2cDev(bus, cfg, d, i, regs))}
        <div class="inline" style="margin-top:6px"><select id="add-${bus}" style="flex:1">
          ${I2C_KNOWN.map((k, j) => html`<option value=${k.c} ?selected=${j === 0}>${k.label}</option>`)}<option value="">other (type compatible)</option></select>
          <button class="sec small" @click=${() => this.addDevice(bus)}>add device</button></div>
      </div>`;
    })}</div>`;
  }

  dialog() {
    if (!this.sel) return html`<dialog></dialog>`;
    const pin = this.sel, pad = this.pad(pin), d = this.draft;
    const funcs = pad ? pad.funcs : ["gpio"];
    const dupes = d.func === "gpio" && d.name ? (this.names()[d.name.trim()] ?? []).filter(k => k !== pin) : [];
    const miss = d.func && d.func !== "gpio" ? partners(d.func).filter(f => !this.funcsInUse().has(f) && f !== (this.spec(pin)?.func)) : [];
    const upd = (k) => (e) => { this.draft = { ...this.draft, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }; };
    return html`<dialog @close=${() => (this.sel = null)}>
      <h3>${pin}</h3>
      <div class="meta">${pad ? html`pad ${pad.pad} · ${pad.pad && pad.modes ? pad.modes : ""}${pad.gpio ? html` · gpio${pad.gpio.join("_")} (line ${pad.gpio[0] * 32 + pad.gpio[1]})` : ""}` : "pad outside the headers"}</div>
      <label>function</label>
      <select .value=${d.func} @change=${upd("func")}>
        <option value="">(not configured)</option>
        ${funcs.map(f => html`<option value=${f} ?selected=${f === d.func}>${f}</option>`)}
        ${pad ? nothing : html`<option value=${d.func} ?selected=${!!d.func}>${d.func || "type below"}</option>`}
      </select>
      ${pad ? nothing : html`<input type="text" style="margin-top:6px" placeholder="function (uart4_rxd, gpio ...)" .value=${d.func} @input=${upd("func")}>`}
      ${d.func === "gpio" ? html`
        <div class="inline">
          <label><input type="radio" name="dir" value="in" ?checked=${d.dir !== "out"} @change=${upd("dir")}> input</label>
          <label><input type="radio" name="dir" value="out" ?checked=${d.dir === "out"} @change=${upd("dir")}> output</label>
        </div>
        ${d.dir === "out" ? html`<label>initial level</label>
          <select .value=${String(d.init ?? 0)} @change=${upd("init")}><option value="0">0 (low)</option><option value="1" ?selected=${Number(d.init) === 1}>1 (high)</option></select>` : nothing}
        <label>pull resistor</label>
        <select .value=${d.pull ?? ""} @change=${upd("pull")}><option value="">default (${d.dir === "out" ? "follows init" : "down"})</option>
          <option value="up" ?selected=${d.pull === "up"}>up</option><option value="down" ?selected=${d.pull === "down"}>down</option><option value="none" ?selected=${d.pull === "none"}>none</option></select>
        <label>line name (alias for libgpiod / OpenPLC: Q0, I3, RS485_DE...)</label>
        <input type="text" .value=${d.name ?? ""} @input=${upd("name")} pattern="[A-Za-z0-9_.-]+">
        ${dupes.length ? html`<div class="err">name already used by ${dupes.join(", ")}</div>` : nothing}
        <label><input type="checkbox" ?checked=${!!d.hog} @change=${upd("hog")}> hog: the kernel owns the line at this level (userspace cannot change it)</label>
      ` : nothing}
      ${miss.length ? html`<div class="partners">this peripheral also needs <b>${miss.join(", ")}</b> on another pin</div>` : nothing}
      <label>comment</label>
      <input type="text" .value=${d.comment ?? ""} @input=${upd("comment")} placeholder="what is connected here">
      <div class="actions">
        ${this.spec(pin) ? html`<button class="danger" @click=${() => this.clearPin()}>Clear pin</button>` : nothing}
        <button class="sec" @click=${() => this.close()}>Cancel</button>
        <button @click=${() => this.apply()} ?disabled=${dupes.length > 0}>Apply</button>
      </div>
    </dialog>`;
  }

  render() {
    if (!this.model) return html`<p class="msg">${this.msg || "loading..."}</p>`;
    const n = this.changes();
    const legend = [["gpio_in", "GPIO in"], ["gpio_out", "GPIO out"], ["uart", "UART"], ["i2c", "I2C"], ["spi", "SPI"], ["pwm", "PWM"], ["can", "CAN"], ["timer", "timer / eQEP"], ["adc", "ADC"], ["reserved", "reserved"], ["free", "free"]];
    return html`
      <div class="bar">
        <button class="sec" ?disabled=${this.busy} @click=${() => this.validate()}>Validate &amp; build</button>
        <button ?disabled=${this.busy || !n && this.model.origin !== "new"} @click=${() => this.save()}>Save${n ? ` (${n} change${n > 1 ? "s" : ""})` : ""}</button>
        <button class="danger" ?disabled=${this.busy} @click=${() => this.flash()}>Save + flash to mtd6</button>
        <button class="sec" @click=${() => this.exportYaml()}>Export YAML</button>
        <button class="sec" ?disabled=${!n} @click=${() => this.undoAll()}>Undo all</button>
        <span class="msg ${this.result ? (this.result.ok ? "ok" : "err") : ""}">${this.msg}</span>
      </div>
      <div class="layout">
        ${this.header("P9")}
        <div class="mid">
          <div class="card"><h4>${this.model.name} <span style="color:var(--mute);font-weight:normal">(${this.model.origin})</span></h4>
            <div class="legend">${legend.map(([c, t]) => html`<span><i style="background:${c === "free" ? "#fff" : `var(--${c})`}"></i>${t}</span>`)}
              <span><i style="border:2px solid #ffd54f"></i>modified</span><span><i style="border:2px solid var(--err)"></i>error</span><span><i style="border:2px solid var(--warn)"></i>peripheral incomplete</span></div>
            <p style="color:var(--mute);margin:8px 0 0">Click a pin to configure it. Analog pins toggle AIN channels. Yellow dot = differs from the saved profile.</p></div>
          <div class="card"><h4>ADC (1.8 V, 12 bit)</h4><div class="adc">${[0, 1, 2, 3, 4, 5, 6].map(ch => html`<label class=${this.model.adc.includes(ch) ? "on" : ""}><input type="checkbox" .checked=${this.model.adc.includes(ch)} @change=${() => this.toggleAdc(ch)} hidden> AIN${ch}</label>`)}</div></div>
          ${this.extraPads()}
          ${this.i2cCard()}
          ${this.result ? html`<div class="card"><h4>${this.result.ok ? "Build OK" : "Build errors"}</h4>
            ${(this.result.errors ?? []).map(e => html`<div class="err">${e.pin ? e.pin + ": " : ""}${e.text}</div>`)}
            ${(this.result.warnings ?? []).map(w => html`<div class="warn">${w.pin ? w.pin + ": " : ""}${w.text}</div>`)}
            ${this.result.ok ? html`<table><tr><th>pin</th><th>pad</th><th>reg</th><th>function</th><th>name</th></tr>
              ${(this.result.pins ?? []).map(p => html`<tr><td>${p.label}</td><td>${p.pad}</td><td>0x${p.offset.toString(16)} = 0x${p.value.toString(16).padStart(2, "0")}</td><td>${p.func}</td><td>${p.name ?? ""}</td></tr>`)}</table>` : nothing}
            </div>` : nothing}
        </div>
        ${this.header("P8")}
      </div>
      ${this.dialog()}`;
  }
}
customElements.define("antminer-board", AntminerBoard);
