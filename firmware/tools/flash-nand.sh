#!/bin/sh
# Provision the Antminer BB-Black V1.8 from a running Linux (netbooted antminer-image or the
# old Angstrom): fetch kernel/DTB/initramfs over TFTP and write them to NAND with verification.
#
#   sh flash-nand.sh [--wipe-config] <tftp-server-ip | /local/dir> [uImage] [am335x-antminer.dtb] [initramfs.cpio.gz.u-boot]
#
# Writes ONLY: mtd6 (fdt), mtd7 (kernel), mtd8 (root). Never touches mtd0..mtd5 (SPL/U-Boot/env):
# the board has no boot button, a broken SPL/U-Boot means JTAG. Reversible with the files in
# nand/recover-nand (am335x-boneblack-bitmainer.dtb, uImage.bin, initramfs.bin.SD) via the same script.
# --wipe-config additionally erases mtd9 (config, jffs2) so Bitmain leftovers (cgminer.conf, shadow,
# a file called "dropbear", ...) are gone; jffs2 formats an erased partition on first mount.
#   sh flash-nand.sh --dtb-only <tftp-server-ip> <board.dtb>     writes only mtd6 (per-board pinmux profile)
set -e
WIPE_CONFIG=0; DTB_ONLY=0
while :; do
    case "$1" in
        --wipe-config) WIPE_CONFIG=1; shift ;;
        --dtb-only) DTB_ONLY=1; shift ;;
        *) break ;;
    esac
done
SERVER="$1"
if [ "$DTB_ONLY" = 1 ]; then
    DTB="${2:-am335x-antminer.dtb}"
else
    KERNEL="${2:-uImage}"
    DTB="${3:-am335x-antminer.dtb}"
    ROOTFS="${4:-antminer-image-antminer-bbb.rootfs.cpio.gz.u-boot}"
fi
[ -n "$SERVER" ] || { echo "usage: $0 [--wipe-config] <tftp-server-ip> [kernel] [dtb] [initramfs] | $0 --dtb-only <tftp-server-ip> <dtb>"; exit 1; }

part_size() { # mtdN -> size in bytes
    awk -v p="$1:" '$1==p { print strtonum("0x"$2) }' /proc/mtd 2>/dev/null || \
    grep "^$1:" /proc/mtd | awk '{ printf "%d\n", "0x"$2 }'
}
mtd_by_name() { grep "\"$1\"" /proc/mtd | cut -d: -f1; }

MTD_FDT=$(mtd_by_name fdt); MTD_KERNEL=$(mtd_by_name kernel); MTD_ROOT=$(mtd_by_name root)
for m in "$MTD_FDT" "$MTD_KERNEL" "$MTD_ROOT"; do
    case "$m" in mtd6|mtd7|mtd8) ;; *) echo "unexpected partition layout ($m), refusing"; exit 1;; esac
done

cd /tmp
if [ "$DTB_ONLY" = 1 ]; then FILES="$DTB"; else FILES="$KERNEL $DTB $ROOTFS"; fi
for f in $FILES; do
    rm -f "$f"
    case "$SERVER" in
        /*)  # a local directory (provisioning SD card: /boot) instead of a TFTP server
            echo ">> copy $SERVER/$f"
            cp "$SERVER/$f" "$f" || { echo "missing $SERVER/$f"; exit 1; } ;;
        *)
            echo ">> tftp $f"
            tftp -g -r "$f" "$SERVER" || { echo "tftp failed for $f"; exit 1; } ;;
    esac
done

check_fit() { # file mtd
    sz=$(stat -c %s "$1"); lim=$(printf "%d" "0x$(grep "^$2:" /proc/mtd | awk '{print $2}')")
    echo "   $1: $sz bytes -> $2 ($lim bytes)"
    [ "$sz" -le "$lim" ] || { echo "   does not fit"; exit 1; }
}
echo ">> size check"
check_fit "$DTB" "$MTD_FDT"
[ "$DTB_ONLY" = 1 ] || { check_fit "$KERNEL" "$MTD_KERNEL"; check_fit "$ROOTFS" "$MTD_ROOT"; }
# sanity: a DTB starts with the magic d00dfeed
[ "$(hexdump -n 4 -e '4/1 "%02x"' "$DTB")" = "d00dfeed" ] || { echo "$DTB is not a DTB"; exit 1; }

flash_one() { # file mtd
    f="$1"; m="$2"; sz=$(stat -c %s "$f")
    echo ">> $m <- $f"
    flash_erase "/dev/$m" 0 0 >/dev/null 2>&1
    nandwrite -p "/dev/$m" "$f" >/dev/null
    want=$(md5sum "$f" | cut -c1-32)
    got=$( { dd bs=2048 count=$((sz / 2048)); [ $((sz % 2048)) -gt 0 ] && dd bs=$((sz % 2048)) count=1; } < "/dev/$m" 2>/dev/null | md5sum | cut -c1-32)
    [ "$want" = "$got" ] && echo "   verified $got" || { echo "   VERIFY FAILED want $want got $got"; exit 1; }
}
# order: root and kernel first, DTB last (a mismatched DTB with the old kernel is the only
# combination that would not boot; both old and new kernels boot with their own DTB)
if [ "$DTB_ONLY" = 1 ]; then
    flash_one "$DTB" "$MTD_FDT"
else
    flash_one "$ROOTFS" "$MTD_ROOT"
    flash_one "$KERNEL" "$MTD_KERNEL"
    flash_one "$DTB" "$MTD_FDT"
fi
if [ "$WIPE_CONFIG" = 1 ]; then
    MTD_CONFIG=$(mtd_by_name config)
    [ "$MTD_CONFIG" = "mtd9" ] || { echo "config partition is not mtd9, not wiping"; exit 1; }
    echo ">> wiping $MTD_CONFIG (config)"
    grep -qs " /config " /proc/mounts && umount /config
    flash_erase -j "/dev/$MTD_CONFIG" 0 0 >/dev/null 2>&1
    echo "   erased with jffs2 clean markers"
fi
sync
echo ">> done. 'reboot -f' boots the new system from NAND."
