# 8. Problems and solutions

## Console and PC

**COM port: "Access to the port is denied".** Another program holds it (most often PuTTY).
Close it. If there is no such program and every attempt hangs, the USB-serial adapter driver
(Prolific) is stuck: unplug the adapter from USB for a few seconds. A symptom of the same thing:
Task Manager does not open. Cause: a forcibly killed process that was waiting on the port; do not
kill such processes, let them time out.

**Nothing on the console.** 115200 8N1, no flow control. TX/RX crossed, common GND, 3.3 V
levels (not RS-232).

**netboot does not download files.** Firewall for UDP 69; the files must be in `firmware/out/`
(`antminer.py stage`); `PC_IP` (`antminer.py config`) must be the PC's IP on the board's network,
otherwise set it in `tools/site.local.conf`.

**antminer.py: "no answer on the serial console".** The board is off, the port is wrong
(`SERIAL_PORT`), or TX/RX are swapped. **"pyserial is missing"**: `pip install pyserial`.

## Boot

**The board always boots from the SD card.** This is by design: U-Boot first looks for `uEnv.txt`
on the card. Power off and remove the card for a NAND boot.

**I removed the card while it was running and nothing happens.** The root was on the card. In an
open shell: `echo b > /proc/sysrq-trigger`. Otherwise cut the power.

**U-Boot: "micro SD card found", then "Unrecognized filesystem type" / "No partition table".**
- Partition 1 must be FAT32 (not exFAT) with an MBR table. Write the `.wic`, do not copy files.
- Some cards do not work in 4-bit mode in some slots (U-Boot "reads" zeros without an error).
  Try another card. Diagnosis from Linux: `dmesg | grep mmc` (`I/O error` = this problem).

**The board restarts by itself after ~60 s.** The hardware watchdog is not being fed: the system
hung before `antminer-early` (rcS S36), or something stopped the `watchdog` daemon. Check on the
console how far the boot gets.

**The overlay disappeared, everything installed is gone.** `antminer-data status`. After 3
consecutive incomplete boots, the overlay is disabled automatically. The data is still on the
partition: fix the cause, `antminer-data enable`, `reboot`.

**The SD system banner has doubled letters.** Old version of the card (fixed 2026-10-07);
write a new `.wic`.

## Network and packages

**`opkg update` cannot download.** Is the feed server running (`antminer.py feed status`),
firewall for TCP 8000, is the IP in `/etc/opkg/base-feeds.conf` correct (04-packages).

**opkg: no space.** `df -h /data`. Clear the lists (`rm -rf /var/lib/opkg/lists/*`) and
unneeded packages; the last resort is `antminer-data wipe`.

**A feed file returns 404, but it exists.** Symlinks in the deploy directory are not served
via `\\wsl$`. Use the name with the date.

**I do not know the board's IP.** Console (`ip addr`), the router's DHCP table (hostname
`antminer-xxxxxx`), or set a static IP in `/config/network`.

## Web UI and OpenPLC

**OpenPLC login does nothing.** The board's clock is wrong (no RTC battery).
`date`; set an NTP server in `/config/ntp-server` or temporarily `date -s "2026-10-07 12:00"`.

**The web UI asks for a password I do not remember.** Delete `/config/web-password` via SSH or the console.

**OpenPLC does not see the inputs/outputs.** The lines must be named exactly `I<n>` / `Q<n>`
(`gpioinfo`). Are they free (`gpioinfo` shows the consumer)? A restart is needed after changing the profile.

**Modbus shows registers the program does not use.** Normal for OpenPLC (07-openplc).

**The ADC shows random values.** The input is floating. Connect it (0..1.8 V!).

## Pinmux and I2C

**The profile does not compile.** The errors are per pin: "reserved for NAND" = the pin is used
by the system; "not available" = the pad does not have that function; "already used" = two pins
with the same pad.

**The I2C device is missing.** The driver must be in the kernel; otherwise the device sits in
`/sys/bus/i2c/devices/` without a `driver`. `i2cdetect -y 2` shows whether the chip responds.
`probe ... failed with error -121` = no chip at this address.

## Build

**Bitbake: missing recipes (python3-flask etc.).** `meta-python` is missing from
`build/conf/bblayers.conf` (old setups). Add
`~/antminer/yocto/meta-openembedded/meta-python`.

**The build stops with "no space".** About 60 GB are needed in WSL. `BB_DISKMON_DIRS` stops the build below 1 GB.

**ParseError: unparsed line.** Bitbake does not allow a comment on an assignment line
(`X = "y"  # comment`); the comment must be on a separate line.

**A kernel config change does not take effect.** The only kernel config is `firmware/kernel/defconfig`;
change it with `bash firmware/build-kernel.sh menuconfig` or `build.sh linux-antminer -c menuconfig`.
Options built as modules (`=m`) do not get into the image: everything must be `=y`.
