#!/bin/bash
# Build a profile the way the board does it: gen-dts.py --flat + dtc only (no cpp, no kernel
# tree). Used to prove the on-target flow on the host and to compare with build-dtb.sh.
#
#   bash build-dtb-flat.sh boards/breakout.yaml     # -> ../out/am335x-antminer-breakout.flat.dtb
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
MAIN=$(cd "$HERE/.." && pwd)
PROFILE="${1:?usage: build-dtb-flat.sh boards/<name>.yaml}"
NAME=$(basename "$PROFILE" .yaml)
OUT="$MAIN/out"
BASE="$OUT/am335x-antminer-base.pp.dtsi"
[ -f "$BASE" ] || bash "$HERE/make-base-pp.sh" "$BASE"
python3 "$HERE/gen-dts.py" "$PROFILE" --flat "$(basename "$BASE")" -o "$OUT/am335x-antminer-$NAME.flat.dts"
dtc -I dts -O dtb -i "$OUT" -o "$OUT/am335x-antminer-$NAME.flat.dtb" "$OUT/am335x-antminer-$NAME.flat.dts" \
    2> >(grep -v -E 'Warning \((unit_address_vs_reg|simple_bus_reg|avoid_unnecessary_addr_size|graph_child_address|spi_bus_bridge|unique_unit_address)\)' >&2 || true)
echo "dtb: $OUT/am335x-antminer-$NAME.flat.dtb ($(stat -c %s "$OUT/am335x-antminer-$NAME.flat.dtb") bytes)"
