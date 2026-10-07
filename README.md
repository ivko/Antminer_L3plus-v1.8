# Antminer BB-Black V1.8 as a Modbus / OpenPLC I/O module

The controller board from the Antminer L3+ (TI AM3352, 256 MB RAM, 256 MB NAND, Ethernet) is
turned into a cheap industrial I/O module: modern Linux (6.12), configurable pins,
Modbus TCP/RTU, OpenPLC, a web interface for provisioning and configuration. Everything related to
mining is removed; from Bitmain only the bootloader in NAND (SPL/U-Boot) and the board wiring remain.

## Where to start

| I want to... | read |
|---|---|
| understand what the board is, how it boots and what is in NAND | [docs/01-overview.md](docs/01-overview.md) |
| prepare a PC and build everything from scratch | [docs/02-build.md](docs/02-build.md) |
| put the system on a board (SD card, NAND, netboot) | [docs/03-install.md](docs/03-install.md) |
| start the feed server and install packages (OpenPLC, web UI) | [docs/04-packages.md](docs/04-packages.md) |
| configure network, hostname, SSH, services, web UI | [docs/05-configure.md](docs/05-configure.md) |
| change what each pin does (pinmux profiles) | [docs/06-pinmux.md](docs/06-pinmux.md) |
| run a PLC program and Modbus | [docs/07-openplc.md](docs/07-openplc.md) |
| fix something that does not work | [docs/08-troubleshooting.md](docs/08-troubleshooting.md) |
| change the code, the recipes or the UI | [docs/09-development.md](docs/09-development.md) |
| see how fast the board reacts (latency measurements, method and results) | [docs/10-latency.md](docs/10-latency.md) |

The shortest path to a working board:
1. Build (WSL): `bash firmware/yocto/setup-yocto.sh` (the first time takes ~2-4 h).
2. Write the card: `powershell -File firmware\tools\write-sd.ps1`.
3. Put the card in the board and power it on. Open the address from the console banner (`http://<ip>/`).
4. In the web UI: NAND → Flash, Init, Enable. Power off, remove the card, power on.

## Repo map

| path | what it is |
|---|---|
| `firmware/` | **the current project**: kernel config, DTS, Yocto layer, pinmux generator, web UI, tools |
| `firmware/yocto/meta-antminer/` | the Yocto layer: machine, distro, recipes, images |
| `firmware/pinmux/` | YAML pin profiles and their generator to device tree |
| `firmware/web/` | the web UI (Flask + Lit component) |
| `firmware/tools/` | tools for the PC: netboot, SD writing, feed server, flashing, OpenPLC test |
| `firmware/dts/` | device tree: the fixed part (`am335x-antminer-base.dtsi`), the generated `am335x-antminer.dts`, a dump of the original Bitmain DTB |
| `firmware/kernel/` | the kernel `defconfig` (it is the source for Yocto) |
| `hardware/breakout/` | KiCad project of a test board with inputs/outputs |
| `docs/` | these guides + reference material (BBB_Pins.xlsx, pinmux PDFs) |
| `docs/history/` | notes from earlier stages, test logs (`device-dump/`) |
| `legacy/` | the original Bitmain system: the factory firmware for restoring, old DTS, scripts and images from the Ångström stage. Not used by `firmware/` |

`firmware/README.md` and `firmware/yocto/README.md` are a development log (what was
tried, why, with what results). Useful for "why is it like this", not for "how to".

## Important rules

- **Never write mtd0-mtd5** (Bitmain SPL, U-Boot, env). The board has no Boot button;
  a broken bootloader means recovery over the serial port or JTAG. All tools write only
  mtd6 (DTB), mtd7 (kernel), mtd8 (initramfs), mtd9 (/config) and mtd10 (data).
- The images are built with `debug-tweaks`: root has **no password** over SSH and on the console. Before a real
  deployment see [docs/05-configure.md](docs/05-configure.md#security).
- The feed server IP address is built into the image at build time (default `192.168.200.104:8000`).
