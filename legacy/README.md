# legacy — оригиналната Bitmain система (Linux 3.8, Ångström 2013.06)

Нищо тук не се ползва от текущия проект (`mainline/`). Пази се за справка и за връщане към
фабричния фърмуер.

| път | какво |
|---|---|
| `bitmain-recovery/` | фабричният фърмуер на контролера: кернел 3.8, initramfs, DTB, uEnv.txt и `runme.sh` от Bitmain recovery картата. MLO и u-boot.img са в `mainline/boot/bitmain/` |
| `dts/` | DTS/DTSI за 3.8. Част от тях вероятно са редактирани при стари експерименти; чистият Bitmain DTB е декомпилиран в `mainline/dts/bitmain/` |
| `images/` | initramfs образи на старата система (original, fixed, nano-mc-opkg) |
| `scripts/` | repack на initramfs, libmodbus, OpenPLC и GPIO инсталатори за Ångström |
| `packages/` | libmodbus 3.1.10 за armv7ahf-vfp-neon |
| `diff/` | дъмпове от старата система (dmesg, pinmux) |

Login на старата система: `root` / `admin`.

## Връщане към фабричния фърмуер

От работеща платка (Yocto системата или SD картата), с TFTP сървър, който сервира
`legacy/bitmain-recovery/` (или файловете копирани в `mainline/out/`):
```sh
cd /tmp && tftp -g -r flash-nand.sh <PC>
sh flash-nand.sh <PC> uImage.bin am335x-boneblack-bitmainer.dtb initramfs.bin.SD
```
Пише само mtd6/7/8. `flash-nand.sh` е в `mainline/tools/`.

**Не пускай `runme.sh`.** Това е скриптът на Bitmain recovery картата: освен кернела и
initramfs-а записва и **u-boot (mtd4) и изтрива env-а (mtd5)**. Ако u-boot.img е повреден или
не е за тази платка, платката няма как да тръгне без сериен или JTAG ремонт.
