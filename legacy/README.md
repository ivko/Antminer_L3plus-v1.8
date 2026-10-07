# legacy — the original Bitmain system (Linux 3.8, Ångström 2013.06)

Nothing here is used by the current project (`firmware/`). It is kept for reference and for reverting to
the factory firmware.

| path | what |
|---|---|
| `bitmain-recovery/` | the factory firmware of the controller: kernel 3.8, initramfs, DTB, uEnv.txt and `runme.sh` from the Bitmain recovery card. MLO and u-boot.img are in `firmware/boot/bitmain/` |
| `dts/` | DTS/DTSI for 3.8. Some of them were probably edited during old experiments; the clean Bitmain DTB is decompiled in `firmware/dts/bitmain/` |
| `images/` | initramfs images of the old system (original, fixed, nano-mc-opkg) |
| `scripts/` | initramfs repack, libmodbus, OpenPLC and GPIO installers for Ångström |
| `packages/` | libmodbus 3.1.10 for armv7ahf-vfp-neon |
| `diff/` | dumps from the old system (dmesg, pinmux) |

Login on the old system: `root` / `admin`.

## Reverting to the factory firmware

From a running board (the Yocto system or the SD card), with a TFTP server serving
`legacy/bitmain-recovery/` (or the files copied into `firmware/out/`):
```sh
cd /tmp && tftp -g -r flash-nand.sh <PC>
sh flash-nand.sh <PC> uImage.bin am335x-boneblack-bitmainer.dtb initramfs.bin.SD
```
Writes only mtd6/7/8. `flash-nand.sh` is in `firmware/tools/`.

**Do not run `runme.sh`.** This is the script of the Bitmain recovery card: besides the kernel and
the initramfs it also writes **u-boot (mtd4) and erases the env (mtd5)**. If u-boot.img is corrupted or
not meant for this board, the board cannot start without a serial or JTAG repair.
