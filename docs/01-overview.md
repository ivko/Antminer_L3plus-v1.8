# 1. The board and the system in brief

## Hardware

| | |
|---|---|
| SoC | TI AM3352 (Cortex-A8, 600 MHz, no PRU and no GPU) |
| RAM | 256 MB DDR3 |
| NAND | 256 MB Micron MT29F2G08 (BCH8 ECC) |
| Network | 100 Mbit Ethernet (SMSC LAN8710) |
| Headers | P8 and P9 as on the BeagleBone Black (2 x 46 pins) |
| Console | UART0, 115200 8N1, 3.3 V TTL (USB-serial adapter) |
| microSD | slot present |
| Missing | eMMC, HDMI, USB port, EEPROM, Reset and Boot buttons |

The board mounts in an original Bitmain carrier board (hash controller) with 4 connectors to the hash
boards, fans, LEDs and a button. This wiring is described in the profile
`firmware/pinmux/boards/default.yaml`.

Without a Reset button the only way to restart is to cut the power or do a software
reboot. That is why the hardware watchdog is always enabled (see 05-configure).

## How the board boots

```
AM3352 ROM ─► SPL (MLO) ─► U-Boot 2013.04 (Bitmain) ─► kernel + DTB + initramfs ─► /init ─► busybox init
```

1. **ROM**. The order of boot sources is fixed by resistors (SYSBOOT). Most boards are
   `0x…13` = NAND, NANDI2C, MMC0, UART0. Some are `0x…17` = MMC0, SPI0, UART0, USB0: these
   boot **only** from an SD card, NAND is not in their list. The value is shown in the first line of
   the console (`Control_status {00420313}`) and on the start page of the web UI.
2. **U-Boot** from NAND (or from the card with `0x17`) first looks for an SD card. If partition 1 has
   `uEnv.txt`, it runs it. Otherwise it reads from NAND:

   | what | from | RAM address |
   |---|---|---|
   | kernel (uImage, ≤ 5 MB) | mtd7 | 0x80200000 |
   | initramfs (≤ 20 MB) | mtd8 | 0x81000000 |
   | DTB (≤ 128 KB) | mtd6 | 0x80F80000 |

   U-Boot has no `bootz`, so the kernel is a legacy uImage. The env partition (mtd5) is empty and the
   built-in env always applies. Autoboot is interrupted with ESC within 1 second.
3. **/init** in the initramfs decides what the root is:
   - `antminer.root=sd` is on the command line (the SD card) → root is ext4 partition 2 on the card;
   - the data partition is formatted and the overlay is enabled → root is overlayfs (initramfs below,
     UBIFS on mtd10 on top), everything written survives a restart;
   - otherwise → root is the initramfs itself in RAM; changes are lost on restart.
4. **busybox init** starts the services from `/etc/rcS.d` and `/etc/rc5.d`.

## NAND partitions

| mtd | name | size | content | who writes it |
|---|---|---|---|---|
| 0-3 | spl, spl_backup1-3 | 4 x 128 KB | Bitmain MLO | **nobody** |
| 4 | u-boot | 1.75 MB | Bitmain U-Boot | **nobody** |
| 5 | bootenv | 128 KB | empty (built-in env) | **nobody** |
| 6 | fdt | 128 KB | DTB (pinmux profile) | flash-nand, antminer-dtb, web UI |
| 7 | kernel | 5 MB | uImage | flash-nand, web UI |
| 8 | root | 20 MB | initramfs | flash-nand, web UI |
| 9 | config | 20 MB | `/config` (jffs2): hostname, SSH keys, network, local profiles | the services; `--wipe-config` erases it |
| 10 | data | 208 MB | UBIFS: persistent overlay (installed packages, OpenPLC programs) | `antminer-data` |

Partition 10 does not exist in the original Bitmain table; it is defined in our DTB and uses
the unused part of NAND after 0x3000000.

## What runs on the board

| service | port | where it comes from |
|---|---|---|
| SSH (dropbear) | 22 | the image |
| web UI for provisioning and configuration | 80 | package `antminer-web` (built into the SD system, optional on NAND) |
| OpenPLC (web) | 8080 | package `openplc-runtime` |
| Modbus TCP (OpenPLC) | 502 | package `openplc-runtime` |
| hardware watchdog (60 s) | | the image |
| ntpd + saving the time to the RTC | | the image (the RTC has no battery) |

Linux sees the inputs/outputs as named GPIO lines (`gpioinfo`), the ADC as IIO
(`/sys/bus/iio/devices/iio:device0`), the UARTs as `/dev/ttyS1..5`, I2C as `/dev/i2c-2`.

## Three images from one build

| image | purpose | file |
|---|---|---|
| `antminer-image` | the system in NAND: initramfs ~5.6 MB + kernel + DTB | `*.rootfs.cpio.gz.u-boot`, `uImage`, `am335x-antminer.dtb` |
| `antminer-provision-image` | provisioning SD card: boot partition + Linux with a web UI that flashes NAND | `*.rootfs.wic` |
| feed (`tmp/deploy/ipk`) | ~2200 ipk packages for `opkg install` (OpenPLC, compiler, Python...) | |

The kernel and the initramfs are the same for NAND and for the card.
