#!/bin/bash
# Pack the opkg feed (tmp/deploy/ipk) into repo/firmware/out, to put it on another web server
# (e.g. ipk.example.com). Run in WSL after a build (antminer.py feed pack calls it).
#
#   bash pack-feed.sh            # without -dbg and -src packages (~0.2 GB instead of ~1.5 GB)
#   bash pack-feed.sh --full     # every package
#
#   out/antminer-feed-<date>.tar.gz          ipk/<arch>/*.ipk + Packages + Packages.gz
#   out/antminer-feed-<date>.tar.gz.sha256
#
# Unpack it into the web root of the server so that http://<server>/ipk/all/Packages.gz works;
# the boards then need "http://<server>" in PACKAGE_FEED_URIS (see docs/04-packages.md).
set -euo pipefail
Y="${Y:-$HOME/antminer/yocto}"
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$(cd "$HERE/.." && pwd)/out"
SRC="$Y/build/tmp/deploy/ipk"
FULL=0; [ "${1:-}" = "--full" ] && FULL=1
[ -s "$SRC/cortexa8hf-neon/Packages" ] || { echo "no feed index in $SRC (build first: bash firmware/yocto/build.sh)"; exit 1; }

NAME="antminer-feed-$(date +%Y%m%d-%H%M)"
# staging tree next to the feed (same file system): hard links, nothing is copied
STAGE=$(mktemp -d "$Y/build/tmp/pack-feed.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT

for d in "$SRC"/*/; do
    arch=$(basename "$d")
    [ -f "$d/Packages" ] || continue
    dst="$STAGE/ipk/$arch"; mkdir -p "$dst"
    if [ $FULL = 1 ]; then
        cp "$d/Packages" "$dst/Packages"
    else
        # drop the index entries of *-dbg and *-src packages (paragraph mode: one stanza per record)
        awk 'BEGIN { RS = ""; FS = "\n"; ORS = "\n\n" }
             { for (i = 1; i <= NF; i++) if ($i ~ /^Package: /) { split($i, a, " "); name = a[2] }
               if (name !~ /-(dbg|src)$/) print }' "$d/Packages" > "$dst/Packages"
    fi
    # only the files the index refers to
    sed -n 's/^Filename: //p' "$dst/Packages" | while read -r f; do ln "$d/$f" "$dst/$f"; done
    gzip -9n < "$dst/Packages" > "$dst/Packages.gz"
    printf "%-16s %5d packages\n" "$arch" "$(grep -c '^Package:' "$dst/Packages")"
done

mkdir -p "$OUT"
tar -C "$STAGE" -czf "$OUT/$NAME.tar.gz" ipk
(cd "$OUT" && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")
echo "$(du -h "$OUT/$NAME.tar.gz" | cut -f1)  $OUT/$NAME.tar.gz"
