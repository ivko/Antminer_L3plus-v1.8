#!/bin/bash
# Build a mainline LTS kernel + DTB for the Antminer BB-Black V1.8 inside WSL2 Ubuntu.
#
#   bash /mnt/e/Antminer/repo/mainline/build-kernel.sh            # clone + build
#   KVER=6.6.y bash .../build-kernel.sh                            # other stable branch
#   bash .../build-kernel.sh dtb                                   # only rebuild the DTB
#
# Sources and build tree live in $WORK (ext4 inside WSL, NOT /mnt/e - 9P is far too slow).
# Results are copied to $REPO/mainline/out/.
set -euo pipefail

KVER="${KVER:-6.12.y}"
WORK="${WORK:-$HOME/antminer}"
REPO="${REPO:-/mnt/e/Antminer/repo}"
JOBS="${JOBS:-$(nproc)}"
OUT="$REPO/mainline/out"
DTS_DIR="arch/arm/boot/dts/ti/omap"

export ARCH=arm
export CROSS_COMPILE=arm-linux-gnueabihf-

if ! command -v arm-linux-gnueabihf-gcc >/dev/null; then
    echo ">> installing toolchain and tools"
    sudo apt-get update
    sudo apt-get install -y crossbuild-essential-armhf u-boot-tools device-tree-compiler \
        bc bison flex libssl-dev libncurses-dev git fakeroot cpio rsync python3
fi

mkdir -p "$WORK" "$OUT"
cd "$WORK"
if [ ! -d linux ]; then
    echo ">> cloning linux-$KVER (shallow)"
    git clone --depth 1 -b "linux-$KVER" \
        https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git linux
fi
cd linux

echo ">> installing board DTS (generated from pinmux/boards/default.yaml) + base dtsi"
cp "$REPO/mainline/dts/am335x-antminer.dts" "$REPO/mainline/dts/am335x-antminer-base.dtsi" "$DTS_DIR/"
if ! grep -q am335x-antminer.dtb "$DTS_DIR/Makefile"; then
    printf '\ndtb-$(CONFIG_SOC_AM33XX) += am335x-antminer.dtb\n' >> "$DTS_DIR/Makefile"
fi

if [ "${1:-}" = "dtb" ]; then
    make -j"$JOBS" dtbs
    cp "$DTS_DIR/am335x-antminer.dtb" "$OUT/"
    echo ">> $OUT/am335x-antminer.dtb"
    exit 0
fi

echo ">> configuring"
make omap2plus_defconfig
scripts/kconfig/merge_config.sh -m .config "$REPO/mainline/kernel/antminer.config"
# SLIM=0 skips the size-trimming fragment (full omap2plus-based kernel, > 5 MiB, netboot only)
if [ "${SLIM:-1}" = "1" ] && [ -f "$REPO/mainline/kernel/antminer-slim.config" ]; then
    scripts/kconfig/merge_config.sh -m .config "$REPO/mainline/kernel/antminer-slim.config"
fi
make olddefconfig
# minimal defconfig of the result; this is what the Yocto kernel recipe (yocto/meta-antminer) builds from
make savedefconfig && cp defconfig "$REPO/mainline/kernel/defconfig"
# show what the fragment asked for but did not stick (renamed/missing symbols)
echo ">> fragment check (symbols that did not end up as requested):"
grep -E '^CONFIG_' "$REPO/mainline/kernel/antminer.config" | while read -r line; do
    grep -qxF "$line" .config || echo "   $line"
done || true

echo ">> building zImage + dtbs with -j$JOBS"
make -j"$JOBS" zImage dtbs

REL=$(make -s kernelrelease)
echo ">> wrapping zImage as legacy uImage (U-Boot 2013.04 has no bootz)"
mkimage -A arm -O linux -T kernel -C none -a 0x80008000 -e 0x80008000 \
    -n "Linux-$REL" -d arch/arm/boot/zImage "$OUT/uImage.bin"

cp arch/arm/boot/zImage "$OUT/zImage"
cp "$DTS_DIR/am335x-antminer.dtb" "$OUT/"
cp .config "$OUT/config-$REL"
cp "$REPO/mainline/sdcard/uEnv.txt" "$OUT/"
cp "$REPO/images/initramfs.bin.SD-fixed" "$OUT/initramfs.bin.SD"

SZ=$(stat -c %s "$OUT/uImage.bin"); LIMIT=$((0x500000))
echo ">> uImage.bin: $SZ bytes, NAND kernel partition limit $LIMIT bytes, margin $((LIMIT - SZ)) bytes"
[ "$SZ" -le "$LIMIT" ] && echo ">> FITS in NAND kernel partition" || echo ">> TOO BIG for NAND kernel partition (netboot only)"

echo
echo ">> done. Copy the contents of $OUT to the FAT partition of the SD card:"
ls -la "$OUT"
