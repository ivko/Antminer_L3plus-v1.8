# legacy — the original Bitmain system (Linux 3.8, Ångström 2013.06)

Nothing here is used by the current project (`firmware/`). It is kept for reference and for reverting to
the factory firmware.

| path | what |
|---|---|
| `201904231534-L3+-SD-recover-NAND.img` | the factory firmware of the controller: kernel 3.8, initramfs, DTB, uEnv.txt and `runme.sh` from the Bitmain recovery card |
| `dts/` | DTS/DTSI for 3.8. Some of them were probably edited during old experiments; the clean Bitmain DTB is decompiled in `firmware/dts/bitmain/` |
| `images/` | initramfs images of the old system (original, fixed, nano-mc-opkg) |
| `scripts/` | initramfs repack, libmodbus, OpenPLC and GPIO installers for Ångström |
| `packages/` | libmodbus 3.1.10 for armv7ahf-vfp-neon |
| `diff/` | dumps from the old system (dmesg, pinmux) |

Login on the old system: `root` / `admin`.

## Reverting to the factory firmware
Boot the board with SD card (`201904231534-L3+-SD-recover-NAND.img`)
