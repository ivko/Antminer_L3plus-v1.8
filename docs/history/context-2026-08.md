# DIY from Scrap --- Context dump

Date: 2026-08-19

## Project: ANTMINER BB-Black V1.8 / L3+ as a general-purpose embedded Linux controller

### 1. Hardware

-   Board: ANTMINER BB-Black V1.8.
-   SoC: TI AM3352 / AM335x, ARM Cortex-A8.
-   The board is BeagleBone Black-like, but it is not a standard BBB.
-   It does not have the standard BeagleBone baseboard EEPROM.
-   The device tree describes 256 MiB RAM: memory { device_type = "memory"; reg
    = \<0x80000000 0x10000000\>; };
-   It uses NAND/GPMC instead of the standard BBB eMMC configuration.
-   Available/described peripherals: Ethernet, USB, MMC/microSD, NAND, GPIO,
    UART, I2C, SPI, PWM, timers, AES/SHA.
-   Described but disabled in the examined DT: PRUSS, CAN0, CAN1, ADC, LCD
    and some of the PWM blocks.
-   There are pinmux conflicts: the same AM335x pads can be
    UART/I2C/SPI and cannot be activated simultaneously without choosing a
    mux.

### 2. Hash boards

-   Antminer L3+/L3++ hash boards are available.
-   They are related to the idea of using the BB-Black outside of its original
    mining function as well.

### 3. Original OS

-   Old Bitmain firmware, based on Ångström/OpenEmbedded.
-   Package manager: opkg.
-   The old public feeds.angstrom-distribution.org is no longer available.
-   An archive of the Ångström v2013.06 binary feeds has been found.
-   Observed structure: feeds/v2013.06/ipk/eglibc/ sdk/ armv7ahf-vfp-neon/
    all/
-   This makes it possible to set up an own local HTTP mirror and to
    restore opkg.

### 4. Script for neutralizing the mining logic

The user is the author of a script that: - replaces /sbin/monitorcg with
an idle loop; - stops cgminer; - kills monitorcg; - installs
angstrom-feed-configs; - runs opkg update; - installs
update-alternatives, ca-certificates, wget; - configures the wget CA
certificate; - starts dropbear; - installs dtc/dtc-dev.

The original dependency on:
http://feeds.angstrom-distribution.org/feeds/v2013.06/... is now broken
and has to be replaced with a local mirror.

### 5. Native build environment

The user has build-libmodbus.sh, which installs directly on the
Antminer: - update-alternatives - wget - autoconf - automake -
libtool - gcc-dev - gcc-symlinks - cpp-symlinks - g++-symlinks -
binutils - make - tar

It then downloads and compiles libmodbus 3.1.10: ./configure --prefix=/usr
--sysconfdir=/etc make && make install

Example application: gcc test.c -o test -I/usr/include/modbus/ -lmodbus

Goal: the BB-Black should be able to serve as a general embedded/industrial Linux
controller, including Modbus.

### 6. Initramfs/NAND repack workflow

The user has an own Bash repacker.

Input: - original initramfs.bin.SD; - new-files.tgz; - optional image
name; - optional output filename.

Workflow: 1. Strips the 64-byte U-Boot legacy image header via tail
-c+65. 2. Extracts the gzip/cpio. 3. Uses fakeroot. 4. Applies
delete.list.txt. 5. Overlays the files from new-files.tgz. 6. Repacks into
newc cpio + gzip. 7. Creates a new U-Boot ramdisk image via mkimage -A
arm -O linux -T ramdisk. 8. Git is used to manage the changes
to the filesystem.

Important: this workflow already works and for now it is not a priority to
optimize it.

### 7. Device Tree workflow

The user compiles an own DTB: dtc am3352-antminer-next.dts -O dtb
-o am3352-antminer-next.dtb

Then writes it directly: flash_erase /dev/mtd6 0x0 0x1 nandwrite -p
/dev/mtd6 am3352-antminer-next.dtb

### 8. NAND layout from the DTS

Described are: - spl: 0x000000, size 0x020000 - spl_backup1: 0x020000, size
0x020000 - spl_backup2: 0x040000, size 0x020000 - spl_backup3: 0x060000,
size 0x020000 - u-boot: 0x080000, size 0x1c0000 - bootenv: 0x240000,
size 0x020000 - fdt: 0x260000, size 0x020000 - kernel: 0x280000, size
0x500000 - root: 0x800000, size 0x1400000 - config: 0x1c00000, size
0x1400000

Therefore /dev/mtd6 is the fdt partition.

Boot chain: AM3352 ROM -\> SPL -\> U-Boot -\> FDT -\> kernel -\>
initramfs/rootfs.

### 9. Device tree files

Examined: - am3352-antminer-next.dts - am335x-boneblack.dtsi -
am335x-bone-common.dtsi - am335x-bone-btm.dtsi -
am335x-boneblack-bitmainer.dts

Important: It is not known for certain what in the local DTS/DTSI files is
original Bitmain and what was edited by the user during old
experiments with the EEPROM. Not everything should automatically be assumed to be
factory source.

### 10. am3352-antminer-next.dts

Looks like an experimental wrapper over am335x-boneblack.dtsi. There are/were
changes around: - disabling i2c0 / internal EEPROM; - enabling
an additional UART. This is probably part of the user's
experiments.

### 11. am335x-bone-btm.dtsi

Contains SPI0/SPI1 pinmux and spidev. SPI max frequency: 16 MHz.

There is an I2C1 configuration on pads 0x180/0x184 and a described PCA9547 at 0x70 with
up to six channels, each with a 24c256 EEPROM at 0x50. i2c1 itself is left
disabled. This I2C/PCA9547/EEPROM part is suspected to be an old
experimental change by the user; it is not proven to be Bitmain
original.

### 12. The EEPROM problem

Two levels have to be distinguished:

Kernel/device-tree: - Linux does not necessarily need a baseboard EEPROM. -
The hardware can be described directly via DT. - The old BBB tree
contains inherited cape/EEPROM infrastructure that can be
disabled.

SPL/U-Boot: - This is the more important unknown layer. - The standard BBB boot
flow can use the EEPROM for board detection and for selecting the DDR
configuration. - The Antminer BB-Black V1.8 evidently boots without a standard
BBB EEPROM. - Therefore the Bitmain SPL/U-Boot probably has a hardcoded
board/DDR setting or some other adaptation.

### 13. Main direction for modernization

Lowest-risk first option: original Bitmain SPL/U-Boot -\>
own DTB -\> newer Linux kernel -\> Debian/Buildroot/other rootfs,
probably from microSD

Advantage: We do not immediately have to solve DDR initialization and EEPROM
board detection in a new SPL.

Next phase: AM3352 ROM -\> own/newer SPL -\> new U-Boot -\>
mainline DTB -\> modern Linux

For this, the original Bitmain U-Boot/SPL has to be analyzed first.

### 14. What has to be established in U-Boot/SPL

-   How the 256 MiB DDR is initialized.
-   How the missing BBB EEPROM is bypassed.
-   NAND geometry.
-   BCH/ECC settings.
-   bootcmd / environment.
-   How the FDT and kernel are loaded.
-   Whether the old U-Boot can directly boot a modern kernel.
-   Whether it can safely boot from microSD without changing the NAND.

### 15. BBB_Pins.xlsx

A file BBB_Pins.xlsx has been uploaded. It contains sheets: - P8 - P9 - Pin Mode
Register Value - Offsets

It is used as an AM335x/BBB pinmux reference: - physical P8/P9 pin; -
ZCZ ball; - signal name; - DT offset; - Mode 0-7; - pin control register
values; - pad offsets.

It is useful for translating: DTS offset/value -\> AM335x pad -\> mux function -\>
physical pin, and vice versa.

### 16. GitHub repository

Repository used: ivko/Antminer_L3plus-v1.8

Raw GitHub links to the DTS/DTSI files were shared. Some URLs
contained temporary token parameters; they should not be used as a
permanent archive.

### 17. Important principle for further work

-   Do not change the working initramfs/repack workflow without a specific
    reason.
-   Do not assume that all DTS/DTSI parts are factory Bitmain.
-   Use the files as a hardware map and compare them with
    original sources/history when possible.
-   The next big target for reverse engineering is U-Boot/SPL.
-   The final DIY goal is to use the board as a cheap general-purpose
    Linux/industrial controller, with particular interest in UART, GPIO, SPI,
    I2C and Modbus.

### 18. Related available resources

The user has at least: - ANTMINER BB-Black V1.8 board/boards; -
L3+ hash boards; - old Bitmain/Ångström firmware; - DTS/DTSI source
collection; - own firmware/initramfs modification workflow; -
Git-based filesystem modifications; - Ångström v2013.06 binary feed
archive; - native GCC build setup; - libmodbus build script; - DTB
compile/flash workflow; - BBB_Pins.xlsx pinmux reference.

This file is a snapshot of the current conversational/technical context and is
intended to be fed back into a future session.
