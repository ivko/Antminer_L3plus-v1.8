#!/bin/bash
# Preprocess the fixed part of the device tree (am335x-antminer-base.dtsi + the kernel's
# am33xx/bone-common includes + dt-bindings headers) into ONE plain .dtsi with no #include
# and no macros. With it, a board profile compiles with dtc alone:
#
#   bash make-base-pp.sh                    # -> ../out/am335x-antminer-base.pp.dtsi
#   python3 gen-dts.py boards/x.yaml --flat am335x-antminer-base.pp.dtsi -o x.dts
#   dtc -I dts -O dtb -i ../out -o x.dtb x.dts
#
# This is what the provisioning SD card / web UI do on the board (package antminer-pinmux),
# so the file is produced at image build time by the same recipe from the same sources.
# KSRC: kernel tree with arch/arm/boot/dts/ti/omap (default ~/antminer/linux).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
MAIN=$(cd "$HERE/.." && pwd)
KSRC="${KSRC:-$HOME/antminer/linux}"
OUT="${1:-$MAIN/out/am335x-antminer-base.pp.dtsi}"
DTSDIR="$KSRC/arch/arm/boot/dts/ti/omap"
[ -f "$DTSDIR/am33xx.dtsi" ] || { echo "kernel tree not found at $KSRC (set KSRC)"; exit 1; }
mkdir -p "$(dirname "$OUT")"
# -P drops the "# line" markers (dtc accepts them, but the file is nicer without)
printf '#include "am335x-antminer-base.dtsi"\n' | \
cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp -P \
    -I "$MAIN/dts" -I "$DTSDIR" -I "$KSRC/arch/arm/boot/dts" -I "$KSRC/include" - \
    | sed '/^[[:space:]]*$/d' > "$OUT.tmp"
# bone-common uses a dtc-style '/include/ "../../tps65217.dtsi"' that cpp leaves alone and that
# only resolves inside the kernel tree: inline such includes (paths relative to the omap dts dir)
python3 - "$OUT.tmp" "$OUT" "$DTSDIR" <<'EOF'
import os, re, sys
src, dst, dtsdir = sys.argv[1:4]
inc = re.compile(r'^\s*/include/\s*"([^"]+)"\s*$')
def expand(text, base):
    out = []
    for line in text.splitlines():
        m = inc.match(line)
        if m:
            path = os.path.normpath(os.path.join(base, m.group(1)))
            with open(path) as fh:
                out.append(f"/* inlined {m.group(1)} */")
                out.append(expand(fh.read(), os.path.dirname(path)))
        else:
            out.append(line)
    return "\n".join(out)
with open(src) as fh:
    body = expand(fh.read(), dtsdir)
body = re.sub(r"^\s*/dts-v1/;\s*$", "", body, flags=re.M)   # the generated .dts declares it
with open(dst, "w") as fh:
    fh.write(body.strip() + "\n")
EOF
rm -f "$OUT.tmp"
# sanity: no leftover preprocessor directives or macros ("#address-cells" is a property, not a directive)
if grep -nE '^\s*#(include|define|if|else|endif)|AM33XX_IOPAD|GPIO_ACTIVE_|^\s*/include/' "$OUT" | head -n 3 | grep .; then
    echo "unexpected preprocessor leftovers in $OUT"; exit 1
fi
echo "base: $OUT ($(wc -c < "$OUT") bytes, $(grep -c . "$OUT") lines)"
