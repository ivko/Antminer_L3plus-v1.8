# 3. Putting the system on a board

Four ways, from the most convenient to the lowest level:

| method | when | writes to NAND |
|---|---|---|
| A. Provisioning SD card + web UI | new board, normal use | yes, from the UI |
| B. netboot over TFTP | development, trying a new kernel/DTB | no |
| C. `flash-nand.sh` from a running board | no card, over the network | yes |
| D. DTB only | changing the pinmux profile | mtd6 only |

First of all: read the board's SYSBOOT (first line on the console, `Control_status`).
`…13` = boots from NAND (the normal case, all boards). `…17` = the ROM boots from the SD card;
you get it by holding P8.43 at 3.3 V during power-on, see the end. The value is latched at
power-on: if it differs from what you expect, check what is connected to the P8 LCD pins
(06-pinmux, SYSBOOT pins).

## A. Provisioning SD card

### 1. Writing the card

The build produces `antminer-provision-image-antminer-bbb.rootfs.wic` (~620 MB). Any card of 1 GB
or more works; the rest of the card is not used.

**Windows** (card in a reader):
```powershell
python firmware\tools\antminer.py stage       # puts the .wic in firmware\out
powershell -File firmware\tools\write-sd.ps1
```
The script lists the USB disks between 1 and 64 GB, asks which one is the card and asks for `YES`. It runs
as administrator (UAC window), wipes the card's partition table, writes the image and verifies
the first 70 MB. Windows will show partition 2 as unknown (ext4) and may offer to
format it: decline.

Other ways: Rufus / balenaEtcher ("DD image" mode), or on Linux:
```sh
sudo dd if=antminer-provision-image-antminer-bbb.rootfs.wic of=/dev/sdX bs=4M conv=fsync status=progress
```

**From a running board** (no reader; the kernel must have MMC, all from 2026-10 do):
```sh
wget -O - http://<PC>:8000/images/antminer-bbb/<the dated file>.wic | dd of=/dev/mmcblk0 bs=1M
sync
```
Afterwards the kernel does not see the new partitions (mdev has mounted the card): either reboot, or
`echo mmc0:XXXX > /sys/bus/mmc/drivers/mmcblk/unbind` and the same with `bind`
(`ls /sys/bus/mmc/drivers/mmcblk/` gives the name).

### 2. Booting from the card

Board powered off → card in the slot → power on. U-Boot from NAND sees `uEnv.txt` on the card and
loads the system from it. After ~20 s a banner appears on the console:

```
========================================================
 Antminer provisioning system (running from the SD card)
   board MAC c4:f3:12:73:1c:92   SYSBOOT 0x00420313
   web UI:  http://192.168.200.116/
   ssh:     root@192.168.200.116 (no password)
========================================================
```

The IP comes from DHCP. Without a console: check the router's DHCP table; the hostname is
`antminer-<last 6 hex digits of the MAC>`.

### 3. Flashing NAND from the web UI

Open `http://<ip>/` → **NAND**:

1. **Scan NAND** shows what is currently in mtd6/7/8 and whether it matches the files on the card.
2. **Flash**: select `uImage`, the DTB (`am335x-antminer.dtb` = profile default, or `profile-<name>.dtb`),
   `initramfs.cpio.gz.u-boot`. On a new board (with Bitmain firmware) tick "also erase /config"
   to remove the old Bitmain settings. Each partition is verified by md5 after writing.
3. **Init** (the data partition): formats mtd10 as UBIFS. Only once per board; erases everything there.
4. **Enable overlay**: from the next boot the root becomes persistent.
5. Power off the board, remove the card, power on. The board boots from NAND (~12 s to login).

The same without the UI, from the shell of the SD system:
```sh
antminer-flash-nand --wipe-config /boot uImage am335x-antminer.dtb initramfs.cpio.gz.u-boot
antminer-data init && antminer-data enable
```

**Remove the card only when the board is powered off.** If you remove it while the system is running from it,
the root disappears and nothing can be executed; `echo b > /proc/sysrq-trigger` in a shell that is still open
restarts the board.

### 4. After the first boot from NAND

Packages (OpenPLC, web UI for the NAND system) → [04-packages.md](04-packages.md).
Network, hostname, SSH keys → [05-configure.md](05-configure.md).

## B. netboot (nothing is written)

The PC runs a TFTP server, the script restarts the board through the console, stops U-Boot, loads
the kernel, DTB and initramfs into RAM and starts them. Good for trying a new kernel or profile.

```powershell
python firmware\tools\antminer.py stage
python firmware\tools\antminer.py netboot                                    # kernel, default DTB, initramfs
python firmware\tools\antminer.py netboot --dtb am335x-antminer-breakout.dtb --log boot.log
```

- Requires the serial port to be free (close PuTTY) and the firewall to allow UDP 69 for python
  (Windows: `netsh advfirewall firewall add rule name="TFTP in" dir=in action=allow protocol=UDP localport=69`).
- The files are looked up in `firmware/out/`; the port and IP come from `site.conf` (`--port` for another port).
- The board must be powered on; the tool sends `reboot` over the console and stops U-Boot.
- `antminer.py uboot "printenv" --then boot` runs arbitrary U-Boot commands the same way.

## C. Flashing from a running board over TFTP

On the board (any system: Yocto, SD, even the old Ångström):
```sh
cd /tmp
tftp -g -r flash-nand.sh <PC>
sh flash-nand.sh [--wipe-config] <PC> uImage-yocto.bin am335x-antminer-yocto.dtb antminer-image.cpio.gz.u-boot
reboot
```
The TFTP server on the PC: `python firmware/tools/antminer.py tftp` (serves `firmware/out/`;
netboot and deploy-dtb start it themselves). The script refuses if the partitions are not where expected, if
a file does not fit, or if the DTB is not a DTB.

## D. DTB only (another pinmux profile)

- from the web UI: Pinmux → profile → **Save + flash to mtd6**;
- on the board: `antminer-dtb build <profile> && antminer-dtb flash /tmp/am335x-antminer-<profile>.dtb`;
- from the PC: `python firmware/tools/antminer.py deploy-dtb <profile>` (`--netboot-only` to try it from RAM).

Details in [06-pinmux.md](06-pinmux.md). Takes effect after a restart.

## Going back to the original Bitmain firmware

The original files are in `legacy/bitmain-recovery/`: `uImage.bin`, `initramfs.bin.SD`,
`am335x-boneblack-bitmainer.dtb`. Copy them to `firmware\out\` and:
```sh
sh flash-nand.sh <PC> uImage.bin am335x-boneblack-bitmainer.dtb initramfs.bin.SD
```
mtd0-5 are never touched, so this is a full restore (without the contents of /config, if it
was erased). Do not use `runme.sh` from the same folder: it also writes u-boot (see `legacy/README.md`).

## Booting from the SD card through the ROM (P8.43 high at power-on)

Normally the ROM never reads the card: NAND comes first in the `…13` order and the Bitmain SPL in
NAND is valid. To make the ROM itself start from the card, hold **P8.43 (SYSBOOT2 = lcd_data2) at
3.3 V (P9.3/P9.4) while the power is applied**. The ROM then latches `…17` = MMC0 first and loads
`MLO` and `u-boot.img` from FAT partition 1 of the card. The provisioning card carries the Bitmain
ones, so the rest of the boot is identical to the normal case. Verified on a board: the
`Control_status {00420317}` in `logs/nand-write-1kom.txt` is this.

Notes:
- A direct wire to 3.3 V was enough; a resistor of a few kΩ is safer against a wrong pin. Remove it
  after the boot: in the `default` profile P8.43 is Q0, and the level must not be there when the
  profile drives the pin (06-pinmux, "The boot order can be changed", for a buffered version).
- Only a power cycle applies it; `reboot` does not re-read SYSBOOT.
- NAND is not touched. This is the recovery path if the SPL/U-Boot in NAND is ever broken, and the
  way to try a new SPL/U-Boot from the card without writing mtd0-4.

The older note about "SD-only boards with a different SYSBOOT2 resistor" was wrong: that reading
came from a board with P8.43 held high, not from a different board. Correction 2026-10-18.
