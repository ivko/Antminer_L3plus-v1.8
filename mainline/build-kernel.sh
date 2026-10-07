#!/bin/bash
# Quick kernel + DTB build without Yocto (inside WSL2 / Linux), for kernel experiments.
# Uses the same kernel/defconfig as the Yocto recipe: that file is the only kernel config.
#
#   bash build-kernel.sh              # clone linux-6.12.y (once) + build -> ../out/uImage.bin, am335x-antminer.dtb
#   bash build-kernel.sh dtb          # only rebuild the DTB
#   bash build-kernel.sh menuconfig   # change options, then writes the result back to kernel/defconfig
#   KVER=6.6.y bash build-kernel.sh   # other stable branch
#
# Sources and build tree live in $WORK (ext4 inside WSL, NOT /mnt/e - 9P is far too slow).
# Results are copied to $REPO/mainline/out/. Test them with tools/netboot.ps1.
set -euo pipefail

KVER="${KVER:-6.12.y}"
WORK="${WORK:-$HOME/antminer}"
REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
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

echo ">> configuring from mainline/kernel/defconfig"
cp "$REPO/mainline/kernel/defconfig" .config
make olddefconfig
if [ "${1:-}" = "menuconfig" ]; then
    make menuconfig
    make savedefconfig && cp defconfig "$REPO/mainline/kernel/defconfig"
    echo ">> written back to mainline/kernel/defconfig (commit it; Yocto builds from it)"
    exit 0
fi

echo ">> building zImage + dtbs with -j$JOBS"
make -j"$JOBS" zImage dtbs

REL=$(make -s kernelrelease)
echo ">> wrapping zImage as legacy uImage (U-Boot 2013.04 has no bootz)"
mkimage -A arm -O linux -T kernel -C none -a 0x80008000 -e 0x80008000 \
    -n "Linux-$REL" -d arch/arm/boot/zImage "$OUT/uImage.bin"

cp arch/arm/boot/zImage "$OUT/zImage"
cp "$DTS_DIR/am335x-antminer.dtb" "$OUT/"
cp .config "$OUT/config-$REL"

SZ=$(stat -c %s "$OUT/uImage.bin"); LIMIT=$((0x500000))
echo ">> uImage.bin: $SZ bytes, NAND kernel partition limit $LIMIT bytes, margin $((LIMIT - SZ)) bytes"
[ "$SZ" -le "$LIMIT" ] && echo ">> FITS in NAND kernel partition" || echo ">> TOO BIG for NAND kernel partition (netboot only)"
echo ">> test without flashing: tools/netboot.ps1 -Kernel uImage.bin -Dtb am335x-antminer.dtb -Initrd antminer-image.cpio.gz.u-boot"
