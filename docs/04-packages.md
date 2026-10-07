# 4. Feed server and installing packages

The image in NAND is minimal (~5.6 MB). Everything larger (OpenPLC with the compiler, Python, the web UI
for the NAND system, tools) is installed with `opkg` from the feed that the build produces, and is stored
on the data partition (overlay).

## Prerequisite: overlay

Without the overlay the root is in RAM and everything installed is lost on restart.

```sh
antminer-data status        # expected: "root: overlay on ubi0:data"
```

If not: `antminer-data init` (only on a new board, erases mtd10), `antminer-data enable`, `reboot`.
The `antminer-data` commands:

| command | what |
|---|---|
| `status` | where the root comes from, used space, failed boot counter |
| `init` | formats mtd10 as UBIFS (erases everything there) |
| `enable` / `disable` | overlay from the next boot / back to plain RAM (the data stays) |
| `wipe` | deletes everything installed (restores the factory image); only with the overlay disabled |
| `mount` | mounts `/data` with the overlay disabled, for inspection |

Protection: if 3 consecutive boots with the overlay do not reach the end of startup, the overlay
disables itself and the board boots from the clean image.

## The feed server

The feed is `~/antminer/yocto/build/tmp/deploy/` in WSL, served over HTTP on port 8000.

```sh
python firmware/tools/antminer.py feed start     # in the background, returns immediately
python firmware/tools/antminer.py feed status
python firmware/tools/antminer.py feed stop
python firmware/tools/antminer.py feed serve     # in the foreground, Ctrl-C stops it
```

It works both on Windows (reads the feed from WSL through `\\wsl$`) and on Linux. The port is `FEED_PORT` from
`site.conf`. Windows Firewall must allow TCP 8000:
```powershell
netsh advfirewall firewall add rule name="opkg feed" dir=in action=allow protocol=TCP localport=8000
```
Check from a browser: `http://<PC>:8000/ipk/all/Packages.gz` downloads.

After each build the index is updated by `package-index` (part of the full build). If you
built only one recipe: `bash firmware/yocto/build.sh package-index`.

### The feed address

The boards look for the feed at the address built in at build time (`FEED_HOST`, default
`192.168.200.104:8000`), in `/etc/opkg/base-feeds.conf`:
```
src/gz uri-all-0 http://192.168.200.104:8000/ipk/all
src/gz uri-cortexa8hf-neon-0 http://192.168.200.104:8000/ipk/cortexa8hf-neon
src/gz uri-antminer_bbb-0 http://192.168.200.104:8000/ipk/antminer_bbb
```
If the PC has a different IP: edit the file on the board (with the overlay the change persists), or
change `PACKAGE_FEED_URIS` in `~/antminer/yocto/build/conf/local.conf` and rebuild the images.

## Installing

```sh
opkg update
opkg install openplc-runtime          # OpenPLC + compiler + Python (~180 packages, ~86 MB)
opkg install antminer-web             # the web UI on the NAND system too (port 80)
opkg list | grep -i <something>       # search
opkg remove <package>
```

Useful packages from the feed:

| package | what |
|---|---|
| `openplc-runtime` | OpenPLC v3 with a hardware layer for the board, web on 8080, Modbus TCP 502 |
| `antminer-web` | web UI: NAND, pinmux editor, settings (port 80) |
| `antminer-pinmux` | `antminer-dtb` and the DTB generator (comes with antminer-web) |
| `libmodbus-dev`, `libgpiod-dev`, `gcc`, `g++`, `make` | for your own C programs on the board |
| `python3`, `python3-pymodbus` | Python and Modbus |
| `i2c-tools`, `libgpiod-tools`, `mtd-utils` | already in the image |

The full list of packages that the build guarantees in the feed is in
`firmware/yocto/meta-antminer/recipes-core/packagegroups/antminer-feed-extras.bb`. The feed
also has everything the build produced along the way (~2200 packages), but not all of it is tested.

## The opkg cache

Downloaded packages are cached in RAM (`/var/volatile/cache/opkg`, `volatile_cache 1` in
`/etc/opkg/antminer.conf`) and are lost on restart, so they do not fill the data partition. The indexes from
`opkg update` are in `/var/lib/opkg/lists` (on the overlay, a few MB):
```sh
rm -rf /var/volatile/cache/opkg/*  /var/lib/opkg/lists/*
df -h /data
```

## Space

The data partition has 185 MB usable. OpenPLC takes ~86 MB. When the partition is full `opkg` stops with an
out-of-space error; `antminer-data wipe` (with the overlay disabled) restores a clean state.
