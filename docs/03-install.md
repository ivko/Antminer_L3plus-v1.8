# 3. Putting the system on a board

Four ways, from the most convenient to the lowest level:

| method | when | writes to NAND |
|---|---|---|
| A. Provisioning SD card + web UI | new board, normal use | yes, from the UI |
| B. netboot over TFTP | development, trying a new kernel/DTB | no |
| C. `flash-nand.sh` from a running board | no card, over the network | yes |
| D. DTB only | changing the pinmux profile | mtd6 only |

First of all: read the board's SYSBOOT (first line on the console, `Control_status`).
`…13` = boots from NAND (the normal case). `…17` = boots **only** from an SD card, see the end.

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

## Boards with SYSBOOT 0x17 (SD only)

The ROM of these boards loads MLO and U-Boot from the card, and NAND is not in the list at all.
They do not boot without a card. With the provisioning card the provisioning system boots, as on the others.

To run the NAND system, the card must stay in the slot, but without `uEnv.txt` (only
`MLO` and `u-boot.img` on FAT partition 1): then U-Boot from the card does not find `uEnv.txt` and reads
the kernel from NAND. **This has not been tested** on such a board.
