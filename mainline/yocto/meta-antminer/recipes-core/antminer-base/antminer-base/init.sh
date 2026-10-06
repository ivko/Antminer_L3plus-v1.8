#!/bin/sh
# /init of the antminer-image initramfs: optional persistent overlay on the NAND "data"
# partition (UBIFS), then hand over to busybox init.
#
#   plain boot:    initramfs (ramfs) is /, everything volatile except /config (jffs2)
#   overlay boot:  / = overlayfs( lower = copy of the initramfs in a tmpfs,
#                                 upper = /data/overlay/upper on UBIFS )
#                  -> opkg installs, config edits, OpenPLC programs survive reboots
#
# The overlay is used only if "antminer-data init" + "antminer-data enable" were run once
# (marker /data/overlay/.enabled). Three consecutive boots that never reach rc5.d S99
# antminer-boot-ok fall back to the plain boot (marker .boot_attempts), and the hardware
# watchdog is armed here so a userspace that hangs before rcS still reboots.
set +e
PATH=/sbin:/usr/sbin:/bin:/usr/bin

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null

# arm the hardware watchdog (60 s default) without the magic close: it keeps running and
# nobody feeds it until rcS.d/S36antminer-early starts /sbin/watchdog
[ -c /dev/watchdog ] && echo -n "" > /dev/watchdog 2>/dev/null

log() { echo "init: $*"; }
plain() {
    log "$1 -> plain ramfs boot"
    umount /dev /sys /proc 2>/dev/null
    exec /sbin/init
}

# --- provisioning SD card: "antminer.root=sd" (uEnv.txt) -> root = ext4 partition 2 ------
# The same kernel + initramfs boot from NAND or from the card; only this bootarg differs.
# The card's rootfs (antminer-provision-image) carries the web UI, dtc, the pinmux generator
# and the NAND payload. NAND is not touched here at all.
case " $(cat /proc/cmdline) " in
*" antminer.root=sd "*|*" antminer.root=sd:"*)
    DEV=$(sed -n 's/.*antminer\.root=sd:\([^ ]*\).*/\1/p' /proc/cmdline)
    DEV=${DEV:-/dev/mmcblk0p2}
    for i in $(seq 1 50); do [ -b "$DEV" ] && break; sleep 0.2; done
    [ -b "$DEV" ] || plain "SD root requested but $DEV never appeared"
    mkdir -p /newroot
    if ! mount -t ext4 -o noatime "$DEV" /newroot 2>/dev/null; then
        plain "cannot mount $DEV (ext4)"
    fi
    [ -x /newroot/sbin/init ] || { umount /newroot; plain "$DEV has no /sbin/init"; }
    log "root on SD card $DEV"
    exec switch_root /newroot /sbin/init
    ;;
esac

MTD=$(grep '"data"' /proc/mtd | cut -d: -f1 | sed 's/^mtd//')
[ -n "$MTD" ] || plain "no data partition"
grep -q 'overlay' /proc/filesystems || plain "no overlayfs in kernel"

# only a UBI-formatted partition attaches; an erased/unused one fails quickly
if ! ubiattach -p "/dev/mtd$MTD" >/dev/null 2>&1; then
    plain "data partition not UBI-formatted (antminer-data init)"
fi
mkdir -p /data
if ! mount -t ubifs -o noatime ubi0:data /data 2>/dev/null; then
    ubidetach -p "/dev/mtd$MTD" >/dev/null 2>&1
    plain "no ubifs volume 'data'"
fi
if [ ! -f /data/overlay/.enabled ]; then
    umount /data; ubidetach -p "/dev/mtd$MTD" >/dev/null 2>&1
    plain "overlay not enabled (antminer-data enable)"
fi

# boot counter: reset by /etc/init.d/antminer-boot-ok at the end of a successful boot
N=$(cat /data/overlay/.boot_attempts 2>/dev/null || echo 0)
case "$N" in ''|*[!0-9]*) N=0 ;; esac
if [ "$N" -ge 3 ]; then
    log "overlay boot failed $N times, disabling it (antminer-data enable to retry)"
    rm -f /data/overlay/.enabled
    echo 0 > /data/overlay/.boot_attempts
    umount /data; ubidetach -p "/dev/mtd$MTD" >/dev/null 2>&1
    plain "overlay disabled after repeated failures"
fi
echo $((N + 1)) > /data/overlay/.boot_attempts
sync

mkdir -p /data/overlay/upper /data/overlay/work /lower /newroot
# lower layer: a tmpfs copy of the initramfs. switch_root deletes the ramfs contents, which
# would pull the lower dir away if we used / directly. ~15 MB of RAM.
mount -t tmpfs -o size=96m,mode=0755 tmpfs /lower || plain "tmpfs for lower layer failed"
for d in /*; do
    case "$d" in /proc|/sys|/dev|/data|/lower|/newroot|/init) continue ;; esac
    cp -a "$d" /lower/ 2>/dev/null
done
# mount points that were skipped above (they are mounts here) must exist in the new root
mkdir -p /lower/proc /lower/sys /lower/dev /lower/data /lower/.lower
if ! mount -t overlay overlay -o lowerdir=/lower,upperdir=/data/overlay/upper,workdir=/data/overlay/work /newroot; then
    umount /lower
    plain "overlay mount failed"
fi
mount --move /data /newroot/data
mount --move /lower /newroot/.lower
log "overlay root on ubi0:data (attempt $((N + 1)))"
# /dev, /proc and /sys stay mounted: switch_root moves them into the new root
exec switch_root /newroot /sbin/init
