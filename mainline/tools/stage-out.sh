#!/bin/bash
# Copy the latest Yocto build results into repo/mainline/out under the fixed names the other
# tools expect (netboot.ps1, deploy-dtb.ps1, flash-nand.sh over TFTP). Run in WSL after a build.
#
#   bash stage-out.sh
#
#   out/uImage-yocto.bin               kernel           (NAND mtd7)
#   out/am335x-antminer-yocto.dtb      default profile  (NAND mtd6)
#   out/am335x-antminer-<profile>.dtb  every profile in pinmux/boards (also built by build-dtb.sh)
#   out/antminer-image.cpio.gz.u-boot  initramfs        (NAND mtd8)
#   out/antminer-provision.wic         whole provisioning SD card
#   out/flash-nand.sh                  provisioning script, fetched by the board over TFTP
set -euo pipefail
Y="${Y:-$HOME/antminer/yocto}"
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$(cd "$HERE/.." && pwd)/out"
D="$Y/build/tmp/deploy/images/antminer-bbb"
mkdir -p "$OUT"
cp -L "$D/uImage" "$OUT/uImage-yocto.bin"
cp -L "$D/am335x-antminer.dtb" "$OUT/am335x-antminer-yocto.dtb"
for f in "$D"/profile-*.dtb; do
    [ -e "$f" ] || continue
    n=$(basename "$f" .dtb); cp -L "$f" "$OUT/am335x-antminer-${n#profile-}.dtb"
done
cp -L "$D/antminer-image-antminer-bbb.rootfs.cpio.gz.u-boot" "$OUT/antminer-image.cpio.gz.u-boot"
[ -e "$D/antminer-provision-image-antminer-bbb.rootfs.wic" ] && \
    cp -L "$D/antminer-provision-image-antminer-bbb.rootfs.wic" "$OUT/antminer-provision.wic"
cp "$HERE/flash-nand.sh" "$OUT/flash-nand.sh"
cd "$OUT" && ls -la uImage-yocto.bin am335x-antminer-*.dtb antminer-image.cpio.gz.u-boot antminer-provision.wic flash-nand.sh 2>/dev/null | awk '{printf "%10s  %s\n", $5, $NF}'
