# 2. Build from scratch

Everything is built with Yocto (scarthgap) in WSL2 on Windows. On plain Linux (Ubuntu 22.04/24.04)
it works the same way; `tools/antminer.py` works on both, only `write-sd.ps1` is Windows-only.

## What the PC needs

| | |
|---|---|
| OS | Windows 10/11 with WSL2 and Ubuntu 24.04 (`wsl --install -d Ubuntu-24.04`) |
| disk | ~60 GB free **inside WSL** (the distribution's ext4 disk): build ~45 GB, downloads ~2 GB, sstate ~2.5 GB |
| RAM / CPU | 16 GB+, and the more cores the faster |
| network | internet for the first build (sources) |
| Windows | Python 3 (for the TFTP/HTTP servers and the tests), Git; optionally PuTTY for the console |
| hardware | 3.3 V USB-serial adapter to the board console (COM port, 115200) |

The repo can be anywhere; the scripts find the path themselves. The examples here use
`E:\Antminer\repo` (in WSL `/mnt/e/Antminer/repo`).

## PC settings: `firmware/tools/site.conf`

The PC's IP on the boards' network, the serial port, the feed port and the path to the Yocto
tree are in one place. Do not edit `site.conf`; create `site.local.conf` next to it (not in
git) with only what differs:
```
PC_IP=192.168.1.20
SERIAL_PORT=/dev/ttyUSB0
```
Empty `PC_IP` = automatic. Check: `python firmware/tools/antminer.py config`.
`antminer.py` needs Python 3.8+ and `pip install pyserial`.

## First build

```sh
# in WSL
bash /mnt/e/Antminer/repo/firmware/yocto/setup-yocto.sh
```

The script:
1. installs the host packages for Yocto (asks for `sudo` once);
2. clones `poky` and `meta-openembedded` (branch scarthgap) into `~/antminer/yocto`;
3. downloads kernel 6.12.112 and checks its sha256;
4. writes `build/conf/local.conf` and `bblayers.conf` (only if they do not exist);
5. starts the full build in the background.

The feed address (`PC_IP:FEED_PORT` from `site.conf`, or `FEED_HOST=ip:port` before the command)
goes into `/etc/opkg/base-feeds.conf` of all images. If the PC has a different IP later,
see [04-packages.md](04-packages.md#the-feed-address).

The first build takes 2-4 hours. Monitoring:

```sh
bash /mnt/e/Antminer/repo/firmware/yocto/build.sh status      # is it running + the last lines
tail -f ~/antminer/yocto/build/bitbake.log
```

The last line of the log is `BITBAKE_EXIT=0` on success.

## Later builds

```sh
bash /mnt/e/Antminer/repo/firmware/yocto/build.sh            # everything, in the background
bash /mnt/e/Antminer/repo/firmware/yocto/build.sh fg         # everything, in the foreground
bash /mnt/e/Antminer/repo/firmware/yocto/build.sh antminer-provision-image   # only one image
```

"Everything" is: `antminer-image`, `antminer-provision-image`, `antminer-feed-image` and
`package-index`. Bitbake rebuilds only the changed parts; a change in the web UI takes a minute,
a change in the kernel ~10 minutes.

## What you get

In `~/antminer/yocto/build/tmp/deploy/images/antminer-bbb/`:

| file | for |
|---|---|
| `uImage` | kernel → NAND mtd7 |
| `am335x-antminer.dtb` | DTB of the `default` profile → NAND mtd6 |
| `profile-<name>.dtb` | DTB of each profile from `firmware/pinmux/boards/` |
| `antminer-image-antminer-bbb.rootfs.cpio.gz.u-boot` | initramfs → NAND mtd8 |
| `antminer-provision-image-antminer-bbb.rootfs.wic` | the whole provisioning SD card |

The feed is in `~/antminer/yocto/build/tmp/deploy/ipk/` (see 04-packages).

Most names are symlinks to files with a date in the name. From Windows (`\\wsl$\...`)
the symlinks often do not open; use the dated file or copy with:

```sh
python firmware/tools/antminer.py stage        # or in WSL: bash firmware/tools/stage-out.sh
```

It puts the latest results in `firmware/out/` under fixed names (`uImage-yocto.bin`,
`am335x-antminer-<profile>.dtb`, `antminer-image.cpio.gz.u-boot`, `antminer-provision.wic`,
`flash-nand.sh`), which netboot, deploy-dtb and write-sd use.

## Reproducibility

- The kernel is pinned: 6.12.112, sha256 in `linux-antminer_6.12.bb`.
- `poky` and `meta-openembedded` are cloned as the latest of branch scarthgap. The build from
  2026-10 uses poky `3a3d07f625ae` and meta-openembedded `0f00f8b9a219`. If a new version
  breaks something, `git checkout` these commits in `~/antminer/yocto/poky` and `meta-openembedded`.
- OpenPLC is pinned to a commit (`SRCREV` in `openplc-runtime_git.bb`).
- `~/antminer/yocto/downloads` contains all sources (~2 GB). With it the build works without internet
  and without the risk that upstream has disappeared. `bash firmware/yocto/backup-downloads.sh` copies it next to the repo
  (`E:\Antminer\backup\yocto-downloads`); on a new machine run `... restore` before `setup-yocto.sh`.

## Cleaning

```sh
bash /mnt/e/Antminer/repo/firmware/yocto/build.sh <recipe> -c cleansstate   # rebuild one recipe from scratch
rm -rf ~/antminer/yocto/build/tmp                                            # rebuild everything (sstate stays, it is fast)
```
