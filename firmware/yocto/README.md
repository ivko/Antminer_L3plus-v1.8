# yocto — Yocto scarthgap image and ipk feed for the Antminer BB-Black V1.8

> **Development log**, not a guide: what was tried, in what order and why, with
> the test results. Some of what is described here was replaced later. For build, installation and
> usage see [docs/](../../docs/) and the [README](../../README.md) in the root.

The `meta-antminer` layer describes the board as a Yocto machine and builds:

- `uImage` of linux-stable 6.12 from `../kernel/defconfig` and `../dts/am335x-antminer.dts` (the very
  same files as build-kernel.sh, there is no second copy);
- `antminer-image`: initramfs for the NAND root partition (20 MB), busybox init + mdev, glibc, dropbear,
  libgpiod, libmodbus, mtd-utils, i2c-tools, opkg;
- ipk feed in `tmp/deploy/ipk` for the boards with more software.

## Status: step 3 done, 2026-10-06

The image was tested via netboot (`device-dump/netboot-09-yocto.log`):

| | |
|---|---|
| initramfs cpio.gz.u-boot | 5.6 MB (limit 20 MB), 52 packages, no eudev |
| uImage | 2.58 MB (limit 5 MB), same defconfig as the netboot kernel |
| boot | kernel 2.4 s, login prompt at ~12 s (DHCP and SSH key generation are most of it) |
| services | busybox init, mdev, watchdog -T 60 -t 10, udhcpc on eth0, dropbear, syslogd |
| /config | jffs2 mtd9 mounted from fstab |
| opkg | `opkg update` and `opkg install libmodbus-dev` from http://PC:8000/ipk, 1659 packages in the feed |

Lessons: without `sysvinit` in DISTRO_FEATURES update-rc.d does not create the rcS.d links and busybox rcS
starts nothing; packagegroup-core-boot uses `?=` for dev_manager and pulls in eudev, so the distro
conf sets VIRTUAL-RUNTIME_* with `=`; poky busybox has no watchdog applet (bbappend with antminer.cfg);
jffs2 does not accept `nofail`.

Known noise at boot: populate-volatile.sh complains about `/var/volatile/tmp/tmp_volatile.NN`.
Harmless, to be fixed later.

## Persistent overlay on the NAND `data` partition (step 5a), 2026-10-06

`/init` in the initramfs (antminer-base) checks whether the data partition (mtd10, 208 MB) is UBI with
a volume `data` and a marker `/data/overlay/.enabled`. If so: it copies the ramfs into tmpfs (lower),
mounts overlayfs with upper/work on UBIFS and does `switch_root`. Everything written to `/`
(opkg install, /etc changes, OpenPLC programs) stays on UBIFS; UBIFS compresses (15.7 MB of
upper take 6.8 MB). Without the marker: a plain ramfs boot as before.

Safeguards: `/init` arms the hardware watchdog before anything else (if userspace does not reach
rcS and the `watchdog` daemon, the board reboots after 60 s); a counter `/data/overlay/.boot_attempts`
is incremented by `/init` and reset by rc5.d/S99antminer-boot-ok, after 3 failed boots the overlay
disables itself. The counter has only been tested in the direction "a successful boot resets it".

```sh
antminer-data init      # one-time: ubiformat + volume "data" (erases the partition)
antminer-data enable    # overlay from the next boot
antminer-data status    # root: overlay on ubi0:data / plain ramfs, used space, counter
antminer-data disable   # back to plain ramfs, the data stays
antminer-data wipe      # clean upper layer (factory image + persistent data partition)
```
Tested: netboot-18/19 (RAM) and nandboot-05 (from NAND).

## OpenPLC v3 (step 5b)

Package `openplc-runtime` in the feed (not in the initramfs): web server on :8080, PLC core sources,
build scripts. OpenPLC compiles every uploaded program on the board with g++, so the package
drags in gcc/g++/binutils/make/libc6-dev/libstdc++-dev (not `packagegroup-core-buildessential`:
that one pulls autoconf/perl, ~60 MB), bash, pkgconfig, libmodbus-dev, libgpiod-dev, Python 3 with
Flask, flask-login, flask-jwt-extended, flask-sqlalchemy, pyserial, pymodbus 2.5.3 (own
recipe, meta-python has 3.x with a different API), python-dotenv (own recipe); pyjwt is without
cryptography (bbappend), otherwise rust comes in. `matiec` (iec2c) is a separate recipe from the same OpenPLC
git. Snap7 is built from the bundled sources, OpenDNP3 is not built: dnp3_dummy.cpp + removed
`-lasiodnp3 ...` from compile_program.sh. The Raspberry-Pi RTS calls in modbus_master.cpp (they exist
only in OpenPLC's libmodbus fork) are wrapped in `#ifdef OPLC_LIBMODBUS_RPI`. Postinst deletes
lto1/lto-dump/ld.gold/dwp (~50 MB). Result on the board: 187 packages, 86 MB of 185 MB on `data`.

Hardware layer: `files/antminer.cpp` (libgpiod v2 + IIO), in the UI it remains "Blank Linux".
Lines named `I0..` from the device tree → `%IX0.0..`, `Q0..` → `%QX0.0..`, ADC AIN0..7 → `%IW0..7`.
Nothing is hard-coded: changing pins means a new YAML profile + DTB.

It is installed on top of the overlay: `opkg update && opkg install openplc-runtime`, started with
`/etc/init.d/openplc start` (rc5.d S90 at boot). From the PC: `tools/openplc-test.py <ip>` logs in with
openplc/openplc, uploads (`--program x.st`, two-step upload like the browser) and compiles a
program (~60 s on the board), starts the PLC and reads coils/registers over Modbus TCP :502.
Verified 2026-10-06 with `../openplc/examples/gpio-echo.st`: Q0 "out hi" and Q1 blinks at 1 Hz in
`/sys/kernel/debug/gpio`, I0..I3 are read as discrete inputs, AIN0 is copied into holding 0.
matiec does not allow `AT %..` and ordinary variables in the same VAR block.
`openplc-test.py <ip> --autostart on --only-settings` enables "Start OpenPLC in RUN mode":
after a reboot the runtime starts the active program by itself (verified, nandboot-11-autostart.log).
The settings (settings POST) must be sent in full: a missing port field disables that
server, and a different device_hostname makes the server call hostnamectl, which the board does not have.
The feed is populated via `antminer-feed-image` (a dummy image), because bitbake of a
packagegroup does not write the ipks of the runtime dependencies. The Flask login cookie requires a correct
clock (RTC without battery → 2018 → login silently fails): `antminer-base-ntp` starts
busybox ntpd at boot and writes the time to the RTC.

## Provisioning SD card (step 6)

`bitbake antminer-provision-image` produces `antminer-provision-image-antminer-bbb.rootfs.wic`:
MBR, p1 FAT32 64 MB (MLO, u-boot.img, uEnv.txt, uImage, am335x-antminer.dtb,
initramfs.cpio.gz.u-boot from `IMAGE_BOOT_FILES`), p2 ext4 ~400 MB with the rootfs. Recipes:
`antminer-sd-boot` (deploys the Bitmain MLO/u-boot.img from `firmware/boot/bitmain` and
`sdcard/uEnv-sd.txt`), `antminer-pinmux` (gen-dts.py, the pad base, the profiles, the preprocessed
base from the kernel source in do_compile, `antminer-dtb`; builds and deploys one DTB per
profile in `boards/`, which wic puts on the card), `antminer-web` (Flask UI from `firmware/web`),
`antminer-provision` (fstab for /boot, banner with the address). The kernel has MMC/ext4/VFAT built in
(in `kernel/defconfig`, not only in the fragment: the recipe reads the defconfig).
Writing the card without a card reader on the PC: from the netbooted board with the MMC kernel
`wget -O - http://<pc>:8000/images/antminer-bbb/<the real name>.wic | dd of=/dev/mmcblk0 bs=1M`
(the feed server serves tmp/deploy; symlinks are not resolved through \\wsl$, use the file with
the timestamp). After dd the kernel does not see the partitions, because mdev has automounted the raw device:
`echo mmc0:XXXX > /sys/bus/mmc/drivers/mmcblk/unbind; echo mmc0:XXXX > .../bind`.
Verified 2026-10-06: boot from the card via the NAND U-Boot, root on ext4, web UI on :80,
`antminer-dtb build default` on the board in 1.6 s gives a DTB byte-identical to the one built by the kernel,
NAND flash via the UI (mtd6/7/8 with md5 verification). The same UI is also installed on the NAND system:
`opkg install antminer-web` (the feed carries it via `antminer-feed-extras`), then
`/etc/init.d/antminer-web start`; there it should be given a password from the Services page
(HTTP basic, `admin`, `/config/web-password`). The test board has it installed on the overlay.

## Structure

| path | role |
|---|---|
| `meta-antminer/conf/machine/antminer-bbb.conf` | tune cortexa8hf-neon, uImage @0x80008000, DTB ti/omap/am335x-antminer.dtb, cpio.gz.u-boot |
| `meta-antminer/conf/distro/antminer.conf` | poky + `INIT_MANAGER = "mdev-busybox"`, glibc, ipk, `DISTRO_FEATURES = "ipv4 largefile"` |
| `meta-antminer/recipes-kernel/linux/linux-antminer_6.12.bb` | kernel tarball from cdn.kernel.org, DTS and defconfig from repo/firmware |
| `meta-antminer/recipes-core/images/antminer-image.bb` | initramfs image, checks the size against 20 MB |
| `meta-antminer/recipes-core/images/antminer-feed-image.bb` | dummy image: builds the ipks from `antminer-feed-extras` for the feed |
| `meta-antminer/recipes-core/antminer-base/` | `/init` with overlay, `antminer-data`, rcS scripts (early/config/boot-ok/ntp), fstab, volatiles, opkg.conf |
| `meta-antminer/recipes-openplc/` | `openplc-runtime` (+ `files/antminer.cpp` hardware layer, init script), `matiec` |
| `meta-antminer/recipes-python/` | pymodbus 2.5.3, python-dotenv, pyjwt without cryptography |
| `../tools/openplc-test.py` | PC: login, upload, compile, start, Modbus TCP read/write |
| `../openplc/examples/` | ST examples for the board |
| `setup-yocto.sh` | WSL: host packages, clone poky/meta-oe, build/conf, bitbake in the background |
| `../tools/serve-feed.ps1` | Windows: HTTP server for `tmp/deploy` (ipk feed) on port 8000 |

The build tree is in WSL: `~/antminer/yocto/{poky,meta-openembedded,build,downloads,sstate-cache}`.
Log of the background build: `~/antminer/yocto/build/bitbake.log`.

## Results (tmp/deploy/images/antminer-bbb/)

- `uImage` → NAND mtd7 (≤ 5 MB)
- `am335x-antminer.dtb` → NAND mtd6
- `antminer-image-antminer-bbb.rootfs.cpio.gz.u-boot` → NAND mtd8 (≤ 20 MB)

They are tested with `tools/netboot.ps1 -Kernel uImage -Dtb am335x-antminer.dtb -Initrd <cpio.gz.u-boot>`
after copying into `firmware/out/`, without touching NAND.

## opkg on the board

`local.conf` sets `PACKAGE_FEED_URIS = "http://192.168.200.104:8000"`, which becomes
`/etc/opkg/*.conf` in the image. On the PC: `powershell -File tools/serve-feed.ps1`, then on the board
`opkg update && opkg install <package>`. In a plain ramfs the installation lasts until reboot; for persistence
the UBIFS `data` partition with overlayfs is used (step 5).

## Notes

- `debug-tweaks` in the image means root without a password. To be removed before real deployment.
- The kernel has no modules, everything is built in; `MODULE_TARBALL_DEPLOY = "0"`.
- Ubuntu 24.04 host: `kernel.apparmor_restrict_unprivileged_userns` does not exist in the WSL kernel,
  bitbake works without changes.
