# firmware — new kernel (mainline Linux) for the Antminer BB-Black V1.8 on top of the old Bitmain U-Boot

> **Development log**, not a guide: what was tried, in what order and why, with
> the test results. Some of what is described here was replaced later. For build, installation and
> usage see [docs/](../docs/) and the [README](../README.md) in the root.

Phase 1 goal: mainline Linux 6.12 LTS boots with the original SPL/U-Boot 2013.04 and
the existing Ångström initramfs, without touching NAND.

## Status: phase 1 achieved on 2026-10-05

Linux 6.12.112 was loaded over the network (U-Boot tftp + bootm, no SD card) and verified:

| check | result |
|---|---|
| NAND mtd0 spl, mtd4 u-boot, mtd6 fdt, mtd7 kernel, mtd8 root | md5 identical to the local files, 0 ECC failures, 14 corrected bits on mtd8 |
| Ethernet | SMSC LAN8710 found, udhcpc gets an address, tftp from the PC works |
| UART | ttyS0 console, ttyS1/2/4/5 hash board |
| PMIC | TPS65217 ID 0xe on i2c0, cpufreq at 600 MHz |
| LED, GPIO | antminer:red/green:status, gpio-line-names visible in /sys/kernel/debug/gpio |
| PWM | pwmchip with 2 channels (ehrpwm0) |

Logs: `device-dump/netboot-01.log` (first attempt, wrong NAND timings), `device-dump/netboot-02.log` (working).

## Step 1 (kernel under 5 MB) and step 2 (NAND write) — done, 2026-10-05

| | omap2plus + fragment | + antminer-slim.config |
|---|---|---|
| uImage.bin | 5.37 MB, does not fit in NAND | **2.46 MB**, 2.66 MB left to the limit |
| kernel code in RAM | 11 MB | 4 MB (Thumb-2, -Os, XZ) |
| boot to shell | 5.9 s | 3.5 s |
| removed | | OMAP2/3/4/5, AM43xx, DRA7, SMP, USB, DRM/FB/VT, sound, IPv6, netfilter, NFS, ext4/vfat, MMC, kprobes/ftrace |
| added | | overlayfs, UBIFS, `data` partition 0x3000000..0x10000000 (208 MB, mtd10) |

Verified on the board: NAND md5 of all partitions OK, Ethernet, ADC 8 channels, PWM, watchdog,
LED, cpufreq 1 GHz. Log: `device-dump/netboot-05-slim-thumb2.log`.

NAND write round-trip on the `data` partition (nothing in the boot partitions was touched):
- Linux 6.12 `nandwrite` block 0 -> U-Boot `nand read` + `crc32` = 8c47c3b4, no ECC errors.
- U-Boot `nand write` block 1 -> Linux `nanddump` md5 matches, 0 ECC messages.
- The OOB bytes of the two writes are identical: mainline BCH8+ELM and U-Boot 2013.04 are the same
  ECC scheme. Provisioning can be done both from U-Boot (tftp + nand write) and from Linux (nandwrite).
- `nand bad` in U-Boot: no bad blocks. Log: `device-dump/uboot-nandtest.log`.

`tools/uboot-cmd.ps1 -Commands @(...) -Then boot|stay` runs arbitrary U-Boot commands over COM3.

Netboot without an SD card: `powershell -File tools/netboot.ps1 -ServerIp <IP of the PC>` starts
`tools/tftp-server.py`, resets the board over COM3, interrupts U-Boot, loads `out/` into RAM and
does bootm. Nothing is written to NAND. The manual commands are in `sdcard/netboot-commands.txt`.

### Lesson on the NAND timings

The first DTS carried the timings from the Bitmain 3.8 DTS (cycle 300 ns, oe-off 150, access 200).
Under 6.12 the OOB was read correctly, but the data was consistently wrong, lagging by 29 to 45 bytes
per page, i.e. missed RE pulses. Cause: `gpmc,access-ns` 200 is after `gpmc,oe-off-ns`
150, so the data is sampled after the NAND has released the bus. The old kernel most likely never
applied these DT values at all, and ran with the registers set by U-Boot:

```
GPMC CS0 CONFIG1..6 from U-Boot 2013.04 (md.l 0x50000060 6):
00000800 001e1e00 001e1e00 16051807 00151e1e 16000f80
-> 8-bit NAND, cycle 300 ns, OE on 70 / off 240 ns, access 210 ns (before OE off)
```

The working solution is the node from mainline `am335x-evm.dts` one to one (same Micron chip):
cycle 82 ns, oe-off 54, access 64, `ti,nand-xfer-type = "prefetch-dma"`.

## Files

| path | purpose |
|---|---|
| `dts/am335x-antminer.dts` | mainline DTS for the board, built on top of `am335x-bone-common.dtsi` |
| `kernel/defconfig` | the only kernel config. Originally it was a `savedefconfig` of omap2plus + two fragments (`antminer.config`, `antminer-slim.config`); the fragments were removed on 2026-10-07 because they had diverged from it |
| `tools/netboot.ps1`, `tools/tftp-server.py`, `tools/uboot-cmd.ps1` | netboot without an SD card and U-Boot commands over COM3 |
| `sdcard/uEnv.txt` | U-Boot env for SD boot with the new addresses and `console=ttyS0` |
| `build-kernel.sh` | WSL2 script: toolchain, clone linux-6.12.y, config, build, mkimage, copies to `out/` |

## Build (WSL2 Ubuntu)

```sh
bash /mnt/e/Antminer/repo/firmware/build-kernel.sh
```

The sources go to `~/antminer/linux` inside WSL (ext4). The result is in `repo/firmware/out/`:
`uImage.bin`, `am335x-antminer.dtb`, `uEnv.txt`, `initramfs.bin.SD` (copy of legacy/images/initramfs.bin.SD-fixed).
Everything in `out/` is copied to the FAT partition of the SD card.

The script prints which symbols from the fragment did not make it into .config. Renamed options
are fixed in `antminer.config`.

## First boot

1. SD in the board, serial console at 115200.
2. U-Boot: `micro SD card found` -> `Loaded environment from uEnv.txt` -> `Running uenvcmd`.
3. The kernel starts with `init=/bin/sh`. In the shell:

```sh
mount -t proc proc /proc; mount -t sysfs sys /sys
cat /proc/mtd                      # expect 10 partitions with the sizes from device-dump/README.md
# md5 of the kernel partition up to the exact size of uImage.bin (busybox head has no -c):
{ dd bs=2048 count=2150; dd bs=368 count=1; } < /dev/mtd7 2>/dev/null | md5sum
#   expected: c68a7b971f6c919dbf34813518bbd6b7  (= nand/recover-nand/uImage.bin)
dmesg | grep -i -E "nand|ecc|elm|mtd|cpsw|phy|mmc"
ls /dev/ttyS*                      # ttyS0 console, ttyS1/2/4/5 hash board UARTs
```

If the md5 of the kernel partition matches `nand/recover-nand/uImage.bin`, the GPMC timings and
BCH8/ELM in the DTS are correct and NAND is safe to write from the new kernel.

## What differs from the old DTB (device-dump/nand-mtd6-fdt.dts)

- UART numbering is mainline: hwmod uartN on 3.8 is `&uart(N-1)`. The console is ttyS0.
- i2c0 with the TPS65217 is enabled (bone-common). The old DTB disabled it, but U-Boot talks to
  the PMIC at 0x24, so it exists. Without it there is no poweroff and no cpufreq.
- `baseboard_eeprom` (i2c0 0x50) and `cape_eeprom0..3` (i2c2 0x54..0x57) from bone-common are
  deleted with `/delete-node/`: there are no EEPROMs on the board, i2c2 shows only what the profile adds.
- `pruss_tm` is disabled, the AM3352 has no PRU-ICSS. bone-common enables it for the AM3358.
- The LEDs on the board are the four BeagleBone user LEDs (gpio1 21..24, heartbeat on usr0),
  verified by blinking. RED=gpio45 and GREEN=gpio23 from the Bitmain scripts are for an LED panel with an IP
  Report button, which this controller does not have. There is no buzzer either.
- `clkout2_pin` from bone-common is NOT applied: on this board pad xdma_event_intr1 (gpio0_20)
  is the buzzer.
- The four hash board UARTs (uart1, uart2, uart4, uart5) are enabled with the pinmux from the original
  Bitmain DTS. ehrpwm0B on P9.29 is the fan PWM.
- The gpio-plc node (broken in the old DTB because of `gpios` instead of `gpio`) is replaced with a pinmux hog
  on P8.43..46 plus `gpio-line-names`, so it can be used with libgpiod: `gpioset -c gpiochip2 8=1`.
- The NAND timings are those from mainline am335x-evm (see the lesson above). ready/busy is via
  `rb-gpios` on gpmc_wait0, not via `gpmc,wait-on-read`.
- `davinci_mdio_default` is redefined with MDIO/MDC only. bone-common adds uart0_ctsn there
  as a GPIO for the PHY reset on BBB rev C, and on this board that is uart4_rxd.
- The SGX module (`/ocp/target-module@56000000`) is disabled, the AM3352 has no SGX.

## GPIO map (from the Bitmain init scripts)

| function | GPIO | sysfs # | pad | DTS name |
|---|---|---|---|---|
| RST0..RST3 (hash board reset) | gpio0_5, 0_4, 0_27, 0_22 | 5, 4, 27, 22 | spi0_cs0, spi0_d1, gpmc_ad11, gpmc_ad8 | rst0..rst3 |
| PLUG0..PLUG3 (board present) | gpio1_19, 1_16, 1_15, 1_12 | 51, 48, 47, 44 | gpmc_a3, gpmc_a0, gpmc_ad15, gpmc_ad12 | plug0..plug3 |
| USR0..USR3 LED on the board | gpio1_21..24 | 53..56 | gpmc_a5..a8 | usr0..usr3 (bone-common leds) |
| RED / GREEN LED (panel, absent) | gpio1_13 / gpio0_23 | 45 / 23 | gpmc_ad13 / gpmc_ad9 | led_red / led_green |
| BEEP (absent on the board) | gpio0_20 | 20 | xdma_event_intr1 | beep |
| RECOVERY key | gpio1_14 | 46 | gpmc_ad14 | recovery_key |
| FAN_SPEED0 / 1 (tach) | gpio3_16 / gpio3_14 | 112 / 110 | mcasp0_axr0 / mcasp0_aclkx | fan_speed0 / 1 |
| FAN_PWM | ehrpwm0B | pwm1 | mcasp0_fsx P9.29 | &ehrpwm0 |
| PLC Q0..Q3 (yours) | gpio2_8, 2_9, 2_6, 2_7 | 72, 73, 70, 71 | lcd_data2,3,0,1 P8.43..46 | plc_q0..q3 |

## Known open questions, to be checked on the hardware

- gpio0_26 (gpmc_ad10) and gpio1_20 (gpmc_a4) are in the Bitmain pinmux, but their function is unclear.
- The labels `&pruss_tm`, `&baseboard_eeprom`, `&epwmss0`, `&ehrpwm0`, `&tscadc` must
  exist in the chosen kernel version. If dtc reports an unknown label, check
  `arch/arm/boot/dts/ti/omap/am33xx*.dtsi` and `am335x-bone-common.dtsi`.

## Step 3 (Yocto initramfs + ipk feed) — done, 2026-10-06

See `yocto/README.md`. Result: `uImage` 2.58 MB, `antminer-image...cpio.gz.u-boot` 5.6 MB,
DTB, ipk feed with 1659 packages. Tested via netboot: watchdog, DHCP, SSH, syslog, /config, opkg.
The old Ångström initramfs is no longer needed for anything.

Provisioning into NAND — done on the test board on 2026-10-06: `tools/flash-nand.sh` on
the netbooted board wrote mtd8, mtd7, mtd6 in that order with md5 verification, then `reboot` loaded
the new system from NAND in ~12 s (log `device-dump/nandboot-01-yocto.log`). The Bitmain kernel and
rootfs are no longer on this board. A second flash with `--wipe-config` also erased the Bitmain files from
/config; now only `ssh/dropbear_rsa_host_key` is there, and it survives a reboot (nandboot-02/03).
The hostname is `antminer-<last 3 bytes of the MAC>`, overridable via `/config/hostname`. The U-Boot default env boots the new kernel without changes:
`console=ttyO0` is redirected to ttyS0 by CONFIG_SERIAL_8250_OMAP_TTYO_FIXUP, `init=/sbin/init`
is busybox init. mtd0..mtd4 (SPL/U-Boot) are never touched, there is no boot button for recovery.
Rolling back: the same script with `nand/recover-nand/{uImage.bin,am335x-boneblack-bitmainer.dtb}`
and `repo/images/initramfs.bin.SD-fixed`.

## Step 4 (per-board device tree from YAML) — done, 2026-10-06

See `pinmux/README.md`. `dts/am335x-antminer-base.dtsi` is the fixed part, `dts/am335x-antminer.dts`
is GENERATED from `pinmux/boards/default.yaml` with `pinmux/gen-dts.py` (not edited by hand).
The per-board profiles produce `out/am335x-antminer-<name>.dtb`, which `tools/deploy-dtb.ps1` writes
to mtd6 (or tries from RAM with `-NetbootOnly`). Verified on the board with `default`,
`example-modbus-rtu` (RS485_DE0..3, DI0/1, hog ALIVE, 4 UART, ADC) and `breakout` (the profile of
the test board `hardware/breakout`, with I2C child nodes; flashed to mtd6 of the test board on
2026-10-06, OpenPLC claims Q0..Q7/I0..I7 after boot): names in gpioinfo, pad
registers exactly as generated, gpioset/gpioget work. All free pads outside the profile are
explicitly set to the reset state (GPIO input pulldown), otherwise a warm reboot keeps old values.
The per-board hostname comes from the MAC, override in /config/hostname; SSH key in /config/ssh.

## ROM boot order and the microSD slot, 2026-10-06

The SYSBOOT pins are read from CONTROL_STATUS (`devmem 0x44E10040`). The test board gives
`0x00420313` → SYSBOOT[4:0] = 10011 = **NAND, NANDI2C, MMC0, UART0**: as long as the SPL in NAND is
valid, the ROM never gets to the SD card; U-Boot from NAND, however, tries SD first (`bootcmd`).
The board from `logs/nand-write-1kom.txt` is `0x00420317` → 10111 = **MMC0, SPI0, UART0, USB0**
(SD only, NAND is not in the list) – a hardware difference in the SYSBOOT2 resistor (= lcd_data2 =
P8.43). I.e. "insert an SD card and it boots from it" applies to the boards with 0x17, not to this one.

The microSD slot: with one particular card (DDINC 16 GB, the old Bitmain card) the test board
reads only in 1-bit mode, and in 4-bit (even at 400 kHz) every read gives `I/O error`; the same
card works in 4-bit on the other board with the old kernel. With another card (USD00 16 GB) 4-bit at
50 MHz runs without a single error on the test board. I.e. the slot is fine, the problem is marginal
card/slot contact. Bitmain U-Boot uses 4-bit, so with a bad combination it "reads" garbage
(`mmc read` returns OK without touching the buffer). Logs: `device-dump/netboot-22..26-*.log`,
`uboot-sdcard-0*.log`. The kernel has MMC/SDHCI_OMAP/VFAT built in (+93 KB) – the basis for
the provisioning SD card; `sdcard/uEnv.txt` is ready (FAT32, partition 1). If a card has problems:
`netboot.ps1 -Dtb am335x-antminer-mmc1bit-fast.dtb` against the standard DTB shows whether it is
a 4-bit problem.

## Provisioning microSD card (step 6), 2026-10-06

One card for both board types: FAT partition 1 carries the Bitmain MLO + u-boot.img (for the boards with
SYSBOOT 10111 the ROM starts from them), `uEnv.txt`, our uImage, DTB and initramfs; ext4 partition 2 is
`antminer-provision-image` (web UI, dtc, the DTS generator). `uEnv.txt` passes
`antminer.root=sd` and `/init` does `switch_root` into partition 2 instead of an overlay on NAND. The
files on partition 1 themselves are also the payload for NAND. The image of the whole card is a `.wic`
(`yocto/meta-antminer/wic/antminer-sd.wks`), written with Rufus/dd or from the board itself.

On the board: `antminer-dtb build <profile>` compiles a YAML profile with dtc on top of a pre-
preprocessed base (`pinmux/make-base-pp.sh`, `gen-dts.py --flat`; the result is byte-identical
to the cpp build), `antminer-dtb flash x.dtb` writes it to mtd6 with verification;
`antminer-flash-nand /boot uImage x.dtb initramfs.cpio.gz.u-boot` flashes mtd6/7/8 from the card.
Web UI (Flask, port 80, `firmware/web/`): board/SYSBOOT, NAND (contents vs. payload, flash,
data partition), pinmux (YAML editor, build, write to mtd6, pin table), services
(hostname, NTP, static IP, SSH keys in /config), log. `antminer-config` now reads
`/config/network` (MODE=static ADDRESS NETMASK GATEWAY DNS) and links `/config/ssh/authorized_keys`.
The `default` profile (from which `dts/am335x-antminer.dts`, the built-in DTB of the image, is generated)
reflects the wiring of the original Bitmain board into which the controller is mounted:
4 UARTs to the hash boards, RST0..3 (outputs, 0 = in reset), PLUG0..3, LED_RED/LED_GREEN,
RECOVERY, IP_SIG, fan PWM + FAN_SPEED0/1, I2C2, plus Q0..3/I0..3 on the LCD pads. Source:
`dts/bitmain/am335x-boneblack-bitmainer.dts` (dtc of `nand/recover-nand/*.dtb`); all 25
Bitmain pads have the same register values. The Bitmain gpio-leds node has wrong line
numbers (plug0, fan_speed0); the pinmux group and the init scripts are authoritative.

Visual pin editor (`/pinmux/<profile>/board`, Lit component
`web/antminer_web/static/board-editor.js` with a vendored `lit-all.min.js`, no build step): P9 and P8
as the physical headers, tiles colored by category (power, reserved, GPIO in/out, UART, I2C,
SPI, PWM, CAN, timer, ADC), click → dialog (function, direction, init, pull, line name, hog,
comment), the AIN tiles toggle the ADC channels, markers for changed/invalid/incomplete peripherals.
JSON API: `/api/pads`, `/api/profiles[/<name>[/build|/flash|/yaml]]`; `gen-dts.py --json` gives
the errors per pin. The profile is stored as YAML (`web/antminer_web/profile.py`, per-pin comments are
in a `comment:` field). Development on the PC: `ANTMINER_PINMUX=.../pinmux ANTMINER_CONFIG=/tmp/cfg
ANTMINER_PAYLOAD=.../out/sdcard python3 run.py --port 8088`, `?open=P8.43` opens the dialog.
Host test: `python3 web/test_smoke.py`. The UI is open as long as there is no password; a password
(HTTP basic, user `admin`) is set from the Services page and lives in `/config/web-password`.

Warning: remove the card **after** reboot/power-off, not while the system is running from it
(the root disappears, nothing can be executed). If it happens: `echo b > /proc/sysrq-trigger`
from the shell (builtin echo) reboots; verified 2026-10-06.

## Next steps

- The old sysfs GPIO numbers do not apply in 6.12, everything goes through libgpiod by `gpio-line-names`.
- Step 5 (done, see `yocto/README.md`): UBIFS on `data` + overlayfs (`antminer-data`),
  OpenPLC as an ipk with a hardware layer for the I*/Q*/ADC lines. Example: `openplc/examples/gpio-echo.st`.
- Not verified: the boot counter fallback (3 failed boots → overlay off); `debug-tweaks`
  (root without password) is still in the image.
- Modbus TCP slave daemon on top of libgpiod/libmodbus as a lighter replacement for OpenPLC in the initramfs.
- The OpenPLC web UI shows the layer as "Blank Linux"; own entry in the list of hardware layers.
