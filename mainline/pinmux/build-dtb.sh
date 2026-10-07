#!/bin/bash
# Generate a board .dts from a YAML profile and compile it to a .dtb (WSL).
#
#   bash build-dtb.sh boards/default.yaml                 # -> ../dts/am335x-antminer.dts + ../out/am335x-antminer-default.dtb
#   bash build-dtb.sh boards/modbus-rtu.yaml              # -> ../out/am335x-antminer-modbus-rtu.dtb (dts kept next to it)
#   KSRC=~/antminer/linux bash build-dtb.sh ...           # kernel tree for am33xx.dtsi / bone-common / dt-bindings
#
# The default profile is special: its .dts is written to dts/am335x-antminer.dts, which is what
# the kernel build (build-kernel.sh and the Yocto recipe) compiles into the image's DTB.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
MAIN=$(cd "$HERE/.." && pwd)
# kernel tree: build-kernel.sh's clone, else the one the Yocto build unpacked
if [ -z "${KSRC:-}" ]; then
    KSRC=$HOME/antminer/linux
    [ -d "$KSRC/arch/arm/boot/dts/ti/omap" ] || KSRC=$HOME/antminer/yocto/build/tmp/work-shared/antminer-bbb/kernel-source
fi
PROFILE="${1:?usage: build-dtb.sh boards/<name>.yaml}"
NAME=$(basename "$PROFILE" .yaml)
OUT="$MAIN/out"
mkdir -p "$OUT"

if [ "$NAME" = "default" ]; then
    DTS="$MAIN/dts/am335x-antminer.dts"
else
    DTS="$OUT/am335x-antminer-$NAME.dts"
fi
DTB="$OUT/am335x-antminer-$NAME.dtb"

python3 "$HERE/gen-dts.py" "$PROFILE" -o "$DTS"

DTSDIR="$KSRC/arch/arm/boot/dts/ti/omap"
[ -f "$DTSDIR/am33xx.dtsi" ] || { echo "kernel tree not found at $KSRC (set KSRC)"; exit 1; }
# the generated dts includes am335x-antminer-base.dtsi from repo/mainline/dts
cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
    -I "$MAIN/dts" -I "$DTSDIR" -I "$KSRC/arch/arm/boot/dts" -I "$KSRC/include" \
    "$DTS" > "$OUT/.$NAME.pp.dts"
dtc -I dts -O dtb -i "$MAIN/dts" -i "$DTSDIR" -o "$DTB" "$OUT/.$NAME.pp.dts" 2> >(grep -v -E 'Warning \((unit_address_vs_reg|simple_bus_reg|avoid_unnecessary_addr_size|graph_child_address|spi_bus_bridge|unique_unit_address)\)|also defined at' >&2 || true)
rm -f "$OUT/.$NAME.pp.dts"
echo "dts: $DTS"
echo "dtb: $DTB ($(stat -c %s "$DTB") bytes)"
