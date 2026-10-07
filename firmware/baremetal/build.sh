#!/bin/bash
# Build the bare-metal programs (WSL / Linux, arm-linux-gnueabihf-gcc from crossbuild-essential-armhf).
#   bash build.sh            # -> ../out/bm-echo.bin (+ .elf, .lst)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/../out"
CROSS=${CROSS:-arm-linux-gnueabihf-}
# -static -no-pie: Ubuntu's gcc links PIE by default, which puts .interp/.dynsym/build-id in front
# of the code; "go" would jump into those. -mgeneral-regs-only: U-Boot leaves VFP/NEON disabled.
CFLAGS="-mcpu=cortex-a8 -marm -O2 -ffreestanding -fno-builtin -nostdlib -nostartfiles -fno-stack-protector \
 -mgeneral-regs-only -fno-tree-vectorize -static -no-pie -Wl,--build-id=none -Wall -Wextra"
mkdir -p "$OUT"
for prog in echo; do
    ${CROSS}gcc $CFLAGS -T "$HERE/link.ld" -o "$OUT/bm-$prog.elf" "$HERE/start.S" "$HERE/$prog.c" -lgcc
    ${CROSS}objcopy -O binary "$OUT/bm-$prog.elf" "$OUT/bm-$prog.bin"
    ${CROSS}objdump -d "$OUT/bm-$prog.elf" > "$OUT/bm-$prog.lst"
    ${CROSS}size "$OUT/bm-$prog.elf"
    ls -la "$OUT/bm-$prog.bin"
done
