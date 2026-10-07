# 5. Configuration: network, services, access

## Accessing the board

| how | details |
|---|---|
| console | COM port of the USB-serial adapter, 115200 8N1 (PuTTY). Login `root`, no password |
| SSH | `ssh root@<ip>`, no password (by default) |
| web UI | `http://<ip>/` (always on the SD system; on the NAND system after `opkg install antminer-web`) |
| OpenPLC | `http://<ip>:8080/`, `openplc` / `openplc` |

The hostname is `antminer-<last 6 hex digits of the MAC>`, for example `antminer-731c92`.

## Where the settings live

Everything specific to one board is on the `/config` partition (NAND mtd9, jffs2). It is not
erased when the system is flashed (except with `--wipe-config` / the checkbox in the UI), and it
is shared by the NAND and SD systems. The files are read at boot by `/etc/init.d/antminer-config`.

| file | what | example |
|---|---|---|
| `/config/hostname` | a hostname to use instead of the MAC-based one | `pump-station-3` |
| `/config/network` | static IP; without this file DHCP is used | see below |
| `/config/ntp-server` | NTP server (first line) | `192.168.200.1` |
| `/config/ssh/authorized_keys` | public SSH keys for root | `ssh-ed25519 AAAA...` |
| `/config/ssh/` | the board's SSH host key (so it does not change on every flash) | |
| `/config/web-password` | the web UI password (hash); without this file the UI is open | |
| `/config/pinmux/*.yaml` | local pinmux profiles saved by the editor | |

All of this can also be set from the web UI, page **Services**.

### Static IP

`/config/network` (shell syntax):
```sh
MODE="static"
ADDRESS="192.168.1.50"
NETMASK="255.255.255.0"
GATEWAY="192.168.1.1"
DNS="192.168.1.1"
```
It is applied at the next boot (or `/etc/init.d/antminer-config start && /etc/init.d/networking restart`).
To go back to DHCP, delete the file.

### Clock

The board has no RTC battery: without a network, the clock starts from the last saved time.
`antminer-ntp` starts `ntpd` at boot and writes the correct time to the RTC. Without internet
access, set an NTP server on the local network in `/config/ntp-server`. A wrong time breaks the
OpenPLC login (the cookie expires immediately).

## Services

Busybox init + SysV scripts. Control: `/etc/init.d/<name> start|stop|restart|status`.

| order | script | what it does |
|---|---|---|
| rcS S04 | `mdev` | devices in /dev |
| rcS S36 | `antminer-early` | directories in /var, the **watchdog** daemon (60 s timeout) |
| rcS S41 | `antminer-config` | mounts /config, hostname, network, SSH keys |
| rc5 S01 | `networking` | eth0 (DHCP or static) |
| rc5 S05 | `antminer-ntp` | ntpd + RTC |
| rc5 S10 | `dropbear` | SSH |
| rc5 S20 | `syslog` | `/var/log/messages` (in RAM) |
| rc5 S20 | `antminer-provision` | SD card only: mounts /boot, shows the banner |
| rc5 S50 | `antminer-web` | web UI on port 80 (if installed) |
| rc5 S90 | `openplc` | OpenPLC (if installed) |
| rc5 S99 | `antminer-boot-ok` | marks a successful boot (resets the overlay counter) |

New service on the board: a script in `/etc/init.d/`, then `update-rc.d <name> defaults`. In a
Yocto recipe: `inherit update-rc.d` (see `antminer-web.bb` as an example).

### Watchdog

`/init` enables the hardware watchdog before the services start, and `antminer-early` starts the
daemon that feeds it. If the system hangs for 60 s, the board restarts by itself. Do not disable
it: the board has no Reset button. For long work without the daemon (debugging),
`/etc/init.d/antminer-early` can be edited, but the board will restart 60 s after the daemon stops.

## Logs

```sh
dmesg | tail
tail -f /var/log/messages          # syslog, in RAM, lost on restart
cat /var/log/antminer-web.log      # web UI
```

## Security

The images are built with `debug-tweaks`: root has no password on SSH and the console, and the web
UI has no password. This is convenient in the lab and unacceptable on a real network. The minimum
before deployment:

1. Put an SSH key in `/config/ssh/authorized_keys` and set a web UI password (Services).
2. Change the OpenPLC password (`openplc`/`openplc`) from its UI.
3. Remove `debug-tweaks` from `IMAGE_FEATURES` in
   `firmware/yocto/meta-antminer/recipes-core/images/antminer-image.bb` and add a root password
   via `EXTRA_USERS_PARAMS` (`inherit extrausers`), rebuild and flash. `passwd` on the board itself
   only works with the overlay and does not survive `antminer-data wipe`.
4. The feed server is plain HTTP without authentication; keep it on a trusted network only.

Modbus TCP has no authentication by design: anyone on the network can write outputs.
