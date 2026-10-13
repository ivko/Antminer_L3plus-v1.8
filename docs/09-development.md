# 9. Development

## What is where (`firmware/`)

| path | role |
|---|---|
| `kernel/defconfig` | the **only** kernel config: used by both Yocto and `build-kernel.sh` |
| `build-kernel.sh` | fast kernel + DTB without Yocto (clones linux-6.12.y into `~/antminer/linux`); `menuconfig` mode for changing the defconfig |
| `dts/am335x-antminer-base.dtsi` | the fixed part of the DTB: NAND and partitions, Ethernet, console, PMIC, SD, LEDs, disabled blocks |
| `dts/am335x-antminer.dts` | **generated** from `pinmux/boards/default.yaml`; do not edit by hand |
| `dts/bitmain/` | dump of the original Bitmain DTB, reference for the wiring |
| `pinmux/gen-dts.py` | the YAML → DTS generator (pad database, reserved pads, checks, `--flat`, `--json`) |
| `pinmux/am335x-bbb-pins.json` | the pad database, extracted from `docs/BBB_Pins.xlsx` with `extract-pins.py` |
| `pinmux/boards/*.yaml` | the profiles |
| `pinmux/build-dtb.sh`, `make-base-pp.sh`, `build-dtb-flat.sh` | DTB build on the PC (cpp) / preprocessed base / build as on the board (dtc only) |
| `web/` | the web UI: `antminer_web/` (Flask), `static/board-editor.js` (Lit component), `test_smoke.py`, `render_page.py` |
| `yocto/meta-antminer/` | the Yocto layer (see below) |
| `yocto/setup-yocto.sh`, `build.sh` | setup and build |
| `tools/` | tools for the PC (see below) |
| `sdcard/uEnv-sd.txt` | `uEnv.txt` of the provisioning card |
| `boot/bitmain/` | the original MLO and u-boot.img (for the card) |
| `openplc/examples/` | ST programs |
| `out/` | build results for TFTP/netboot (in .gitignore) |

### The Yocto layer

| | |
|---|---|
| `conf/machine/antminer-bbb.conf` | cortexa8hf-neon, uImage at 0x80008000, DTB, initramfs format |
| `conf/distro/antminer.conf` | poky + busybox init/mdev, glibc, ipk, `sysvinit` in DISTRO_FEATURES |
| `recipes-kernel/linux/linux-antminer_6.12.bb` | kernel from tarball + `kernel/defconfig` + the DTS files from the repo |
| `recipes-core/images/antminer-image.bb` | the NAND image (checks the 20 MB limit) |
| `recipes-core/images/antminer-provision-image.bb` + `wic/antminer-sd.wks` | the SD card |
| `recipes-core/images/antminer-feed-image.bb` | dummy image, makes bitbake write the ipk files of the feed packages |
| `recipes-core/packagegroups/antminer-feed-extras.bb` | which packages are guaranteed to be in the feed |
| `recipes-core/antminer-base/` | `/init` (overlay, SD root, watchdog), `antminer-data`, rcS scripts, fstab, opkg settings |
| `recipes-core/antminer-pinmux/` | the generator, the profiles and `antminer-dtb` on the board |
| `recipes-core/antminer-web/`, `antminer-provision/` | the web UI, banner and /boot on the card |
| `recipes-bsp/antminer-sd-boot/` | MLO, u-boot.img, uEnv.txt for wic |
| `recipes-openplc/` | OpenPLC runtime (with the hardware layer `files/antminer.cpp`) and matiec |
| `recipes-python/` | pymodbus 2.5.3, python-dotenv, pyjwt without cryptography |
| `recipes-core/{busybox,dropbear,init-ifupdown}` | bbappends: busybox applets (watchdog, ntpd, devmem...), dropbear key on /config, interfaces |

The layer is read directly from the repo (`bblayers.conf` points to `/mnt/e/.../meta-antminer`),
and the recipes take files from `firmware/` via `ANTMINER_FIRMWARE_DIR`: there are no copies.

### Tools (`tools/`)

| | where | what |
|---|---|---|
| `antminer.py` | Windows, Linux | everything with the board from the PC: `config`, `console`, `uboot`, `netboot`, `deploy-dtb`, `feed`, `tftp`, `stage` |
| `site.conf` (+ `site.local.conf`) | | the PC settings: IP, serial port, feed port, Yocto path |
| `stage-out.sh` | WSL/Linux | copies the build results into `out/` (called by `antminer.py stage`) |
| `write-sd.ps1` | Windows | writes a `.wic` to an SD card (on Linux: `dd`) |
| `tftp-server.py` | | the TFTP server that `antminer.py` uses (can also run standalone) |
| `*.ps1` (netboot, deploy-dtb, uboot-cmd, serial, feed-server-*, serve-feed) | Windows | the previous versions of `antminer.py`; will be removed |
| `flash-nand.sh` | the board | flashes mtd6/7/8 from TFTP or a local directory (= `antminer-flash-nand`) |
| `openplc-test.py` | PC | uploads/compiles/starts an OpenPLC program, reads Modbus |

## Common changes

**Package in the NAND image.** `CORE_IMAGE_EXTRA_INSTALL` in `antminer-image.bb`. Watch the
20 MB limit (the build stops above it). Larger things → feed (`antminer-feed-extras.bb`).

**Kernel option.** `bash firmware/build-kernel.sh menuconfig` (writes back to
`firmware/kernel/defconfig`), then rebuild `linux-antminer`. Modules are not packaged:
everything must be `=y`. The kernel limit in NAND is 5 MB.

**New pin profile.** Create it in the editor (it saves to `/config/pinmux/` on the board) and
download it with Export YAML into `firmware/pinmux/boards/`, so that it gets into the images and
onto the card.

**Changing the fixed part of the DTB.** `dts/am335x-antminer-base.dtsi`. If you take a new pad,
add it to `RESERVED` in `gen-dts.py`, so the generator does not give it to the profiles.

**Web UI.** See [The web UI test server on the PC](#the-web-ui-test-server-on-the-pc) below.

## The web UI test server on the PC

The web UI (`firmware/web/`) runs in WSL against the files in the repo, without a board and
without a build. Use it for the pin editor, the page layout and the profile YAML.

Once, in WSL: `sudo apt install python3-flask python3-yaml`.

Start it from PowerShell (the window stays busy, Ctrl+C stops it):
```powershell
wsl -e bash -c "cd /mnt/e/Antminer/repo/firmware/web && mkdir -p /tmp/cfg-dev && ANTMINER_PINMUX=/mnt/e/Antminer/repo/firmware/pinmux ANTMINER_CONFIG=/tmp/cfg-dev python3 run.py --port 5000 --debug"
```
or in a WSL shell:
```sh
cd /mnt/e/Antminer/repo/firmware/web
mkdir -p /tmp/cfg-dev
ANTMINER_PINMUX=../pinmux ANTMINER_CONFIG=/tmp/cfg-dev ANTMINER_PAYLOAD=../out/sdcard python3 run.py --port 5000 --debug
```

Then open in the browser of the PC:

| URL | what |
|---|---|
| `http://localhost:5000/` | the start page (board facts are empty on the PC) |
| `http://localhost:5000/pinmux` | the profile list |
| `http://localhost:5000/pinmux/default/board` | the visual pin editor for profile `default` (or `breakout`, `example-modbus-rtu`, a new name) |

The environment variables:

| variable | on the board | for the test server |
|---|---|---|
| `ANTMINER_PINMUX` | `/usr/share/antminer/pinmux` | `firmware/pinmux` of the repo: the shipped profiles, `gen-dts.py`, the pad database |
| `ANTMINER_CONFIG` | `/config` | a scratch directory: **Save** writes `<dir>/pinmux/<name>.yaml` there, never into the repo |
| `ANTMINER_PAYLOAD` | `/boot` | optional: the files the NAND page offers for flashing |

`--debug` reloads the Python code on every change; after a change in `static/board-editor.js`
or the templates, reloading the page is enough. `--port 80` (the default) needs root, so use a free
port above 1024.

What does **not** work on the PC, because the tools exist only on the board:
- **Validate & build** and **Save + flash** (`/usr/sbin/antminer-dtb`), the NAND page (`mtd`,
  `nanddump`), the data partition, Reboot;
- the board facts: no `devmem`, so the SYSBOOT card in the editor says "Board value not available"
  and flags every boot-relevant SYSBOOT pin in red. With the real strap levels this happens only on the board.

To check a profile on the PC, build it with the generator instead:
`python3 ../pinmux/gen-dts.py ../pinmux/boards/breakout.yaml -o /tmp/t.dts --json /tmp/t.json`
(the same errors and warnings the editor shows after Validate).

Before a commit: `python3 test_smoke.py` (all pages + YAML round-trip conversion of the profiles).

**On a board, without a rebuild:** copy the changed files and restart the service:
```sh
scp -r firmware/web/antminer_web root@<ip>:/usr/share/antminer/web/
ssh root@<ip> /etc/init.d/antminer-web restart
```
The UI is then on `http://<ip>/` with everything working. If gen-dts.py changed too, copy it
to `/usr/share/antminer/pinmux/`, because the UI on the board loads the generator from there.

## Checks before commit

```sh
python3 firmware/web/test_smoke.py
bash firmware/pinmux/build-dtb.sh firmware/pinmux/boards/default.yaml   # regenerates am335x-antminer.dts
bash firmware/yocto/build.sh fg
```
If `default.yaml` is changed, `dts/am335x-antminer.dts` must be in the same commit.

## Hardware facts not visible from the code

- The Bitmain 3.8 kernel numbers `uart1..6` and `gpio1..4`; mainline uses `uart0..5`, `gpio0..3`.
- The NAND timings in the DTS are from am335x-evm; the Bitmain ones give corrupted data with the new driver.
- U-Boot 2013.04 has no `bootz`: the kernel is a uImage, load address 0x80008000.
- The ADC is 1.8 V, 12 bit; `ti,am335-sdhci` (not omap_hsmmc) is the microSD driver in 6.12.
- The detailed history (what was tried and why) is in `firmware/README.md` and `firmware/yocto/README.md`.
