#!/bin/bash
# Quick kernel + DTB build without Yocto (inside WSL2 / Linux), for kernel experiments.
# Uses the same kernel/defconfig as the Yocto recipe: that file is the only kernel config.
#
#   bash build-kernel.sh              # clone linux-6.12.y (once) + rt patch + build -> ../out/uImage.bin, am335x-antminer.dtb
#   bash build-kernel.sh dtb          # only rebuild the DTB
#   bash build-kernel.sh menuconfig   # change options, then writes the result back to kernel/defconfig
#   KVER=6.6.y bash build-kernel.sh   # other stable branch (needs a matching RT_PATCH, or RT=0)
#   RT=0 bash build-kernel.sh         # plain kernel (PREEMPT none, unpatched tree) -> ../out/uImage-plain.bin,
#                                     # only for comparisons; the fleet kernel is PREEMPT_RT since 2026-11-03
#
# PREEMPT_RT: the fleet defconfig has CONFIG_PREEMPT_RT=y. 32-bit ARM has no ARCH_SUPPORTS_RT in
# mainline 6.12, so the build uses a second worktree of the same tag ($WORK/linux-rt) with the
# external 6.12-rt patch applied (the same patch as the Yocto recipe linux-antminer_6.12.bb).
#
# Sources and build tree live in $WORK (ext4 inside WSL, NOT /mnt/e - 9P is far too slow).
# Results are copied to $REPO/firmware/out/. Test them with tools/netboot.ps1.
set -euo pipefail

KVER="${KVER:-6.12.y}"
WORK="${WORK:-$HOME/antminer}"
REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
JOBS="${JOBS:-$(nproc)}"
OUT="$REPO/firmware/out"
DTS_DIR="arch/arm/boot/dts/ti/omap"
RT="${RT:-1}"
RT_PATCH="${RT_PATCH:-patch-6.12.111-rt21.patch.xz}"   # https://cdn.kernel.org/pub/linux/kernel/projects/rt/6.12/
RT_URL="https://cdn.kernel.org/pub/linux/kernel/projects/rt/${KVER%.y}/${RT_PATCH}"

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

if [ "$RT" = "1" ]; then
    # second worktree at the same stable tag, so the plain tree stays untouched
    TAG=$(git describe --tags --exact-match 2>/dev/null || git rev-parse HEAD)
    if [ ! -d "$WORK/linux-rt" ]; then
        echo ">> creating worktree linux-rt at $TAG"
        git worktree add "$WORK/linux-rt" "$TAG"
    fi
    cd "$WORK/linux-rt"
    mkdir -p "$WORK/rt-dl"
    if [ ! -f "$WORK/rt-dl/$RT_PATCH" ]; then
        echo ">> downloading $RT_URL"
        curl -sSL -o "$WORK/rt-dl/$RT_PATCH" "$RT_URL"
    fi
    if [ ! -f .rt-applied ]; then
        echo ">> applying $RT_PATCH on $(git describe --tags)"
        xz -dc "$WORK/rt-dl/$RT_PATCH" | git apply --check
        xz -dc "$WORK/rt-dl/$RT_PATCH" | git apply
        echo "$RT_PATCH" > .rt-applied
    else
        echo ">> $(cat .rt-applied) already applied"
    fi
fi

echo ">> installing board DTS (generated from pinmux/boards/default.yaml) + base dtsi"
cp "$REPO/firmware/dts/am335x-antminer.dts" "$REPO/firmware/dts/am335x-antminer-base.dtsi" "$DTS_DIR/"
if ! grep -q am335x-antminer.dtb "$DTS_DIR/Makefile"; then
    printf '\ndtb-$(CONFIG_SOC_AM33XX) += am335x-antminer.dtb\n' >> "$DTS_DIR/Makefile"
fi

if [ "${1:-}" = "dtb" ]; then
    make -j"$JOBS" dtbs
    cp "$DTS_DIR/am335x-antminer.dtb" "$OUT/"
    echo ">> $OUT/am335x-antminer.dtb"
    exit 0
fi

echo ">> configuring from firmware/kernel/defconfig"
cp "$REPO/firmware/kernel/defconfig" .config
if [ "$RT" != "1" ]; then
    # comparison build: the only difference to the fleet defconfig is the preemption model
    scripts/config --disable PREEMPT_RT --enable PREEMPT_NONE
fi
make olddefconfig
if [ "$RT" = "1" ] && ! grep -q "^CONFIG_PREEMPT_RT=y" .config; then
    echo "!! CONFIG_PREEMPT_RT did not stick (is the rt patch applied? EXPERT set?)"; exit 1
fi
if [ "${1:-}" = "menuconfig" ] && [ "$RT" != "1" ]; then
    echo "!! menuconfig only in the RT tree (the default): the saved defconfig must keep PREEMPT_RT"; exit 1
fi
if [ "${1:-}" = "menuconfig" ]; then
    make menuconfig
    make savedefconfig && cp defconfig "$REPO/firmware/kernel/defconfig"
    echo ">> written back to firmware/kernel/defconfig (commit it; Yocto builds from it)"
    exit 0
fi

echo ">> building zImage + dtbs with -j$JOBS"
make -j"$JOBS" zImage dtbs

REL=$(make -s kernelrelease)
SUFFIX=""; [ "$RT" = "1" ] || SUFFIX="-plain"
echo ">> wrapping zImage as legacy uImage (U-Boot 2013.04 has no bootz)"
mkimage -A arm -O linux -T kernel -C none -a 0x80008000 -e 0x80008000 \
    -n "Linux-$REL" -d arch/arm/boot/zImage "$OUT/uImage$SUFFIX.bin"

cp arch/arm/boot/zImage "$OUT/zImage$SUFFIX"
cp "$DTS_DIR/am335x-antminer.dtb" "$OUT/"
cp .config "$OUT/config-$REL"

SZ=$(stat -c %s "$OUT/uImage$SUFFIX.bin"); LIMIT=$((0x500000))
echo ">> uImage$SUFFIX.bin: $SZ bytes, NAND kernel partition limit $LIMIT bytes, margin $((LIMIT - SZ)) bytes"
[ "$SZ" -le "$LIMIT" ] && echo ">> FITS in NAND kernel partition" || echo ">> TOO BIG for NAND kernel partition (netboot only)"
echo ">> test without flashing: tools/netboot.ps1 -Kernel uImage$SUFFIX.bin -Dtb am335x-antminer.dtb -Initrd antminer-image.cpio.gz.u-boot"
