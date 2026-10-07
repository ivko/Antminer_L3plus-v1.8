# Ångström 3.8 stage (2025)

The initial work was on the original Bitmain system (Linux 3.8.13, Ångström
2013.06, login `root` / `admin`): initramfs repack, old DTS, libmodbus, OpenPLC on
the old kernel. The files from this stage are in `legacy/` (described in `legacy/README.md`), together with
the factory firmware for reverting (`legacy/bitmain-recovery/`).

`context-2026-08.md` in this directory is a note from August 2026, before the mainline port.
`device-dump/` contains the logs from the mainline port tests (netboot, NAND boot, U-Boot
sessions, dump of the original NAND DTB); the logs in `firmware/README.md` and
`firmware/yocto/README.md` cite them as `device-dump/...`.

## The previous README of the repo

```
# Antminer_L3plus-v1.8
Linux version 3.8.13 (xxl@armdev01) (gcc version 4.7.4 20130626 (prerelease) (Linaro GCC 4.7-2013.07) ) #22 SMP Tue Dec 2 15:26:11 CST 2014

## Tasks
- Make a new flasher image with following requirements:
  - Make the size smaller by removing unused software on it
  - Make it interactive:
    - ask to approve flashing the coresponding nand
    - ask to choose what source to be flashed by listing avalable sources indexed by number for each section of the nand, u-boot, uImage, dtb
- Add dts source files from https://github.com/derekmolloy/boneDeviceTree/blob/master/DTSource3.8.13
- Make a repo with "new-files" to save space in the repo. Leave just one .SD image file as a source (initramfs.bin.SD-fixed)
- Make one dtd with UART1 enabled and all GPIOs enabled (testing libmodbus).
- Build libmodbus.apk with required dependencies.
## Login
- root:admin
## Pin Mux Modes:
- https://www.ofitselfso.com/BeagleNotes/BeagleboneBlackPinMuxModes.php
## GPIOs:
- https://vadl.github.io/beagleboneblack/2016/07/29/setting-up-bbb-gpio
## Bitmianer recipe:
- https://github.com/ivko/Antminer_firmware/blob/master/sources/meta-antminer/recipes-bitmianer/dtb/bitmainer-dtb-1.0/am335x-boneblack.dts
## links:
- https://github.com/RobertCNelson/bb.org-overlays/blob/master/src/arm/cape-CBB-Serial-r01.dts
## Notes
opkg update && opkg install update-alternatives eglibc-staticdev module-init-tools kernel-module-iio-trig-sysfs kernel-module-iio-trig-gpio
```
