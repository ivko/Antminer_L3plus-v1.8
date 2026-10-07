#!/bin/bash
# One-shot Yocto (scarthgap) setup + build for the Antminer I/O module, inside WSL2 Ubuntu 24.04.
#
#   bash /mnt/e/Antminer/repo/mainline/yocto/setup-yocto.sh            # setup + full build (background, logs to build/bitbake.log)
#   bash /mnt/e/Antminer/repo/mainline/yocto/setup-yocto.sh setup      # only clone/configure, no build
#   bash /mnt/e/Antminer/repo/mainline/yocto/setup-yocto.sh fg         # build in the foreground
#
# Variables: Y (build tree, default ~/antminer/yocto), REPO (this repository, default: found from
# the script's location), FEED_HOST (ip:port of the PC that serves the opkg feed; it is baked into
# /etc/opkg/base-feeds.conf of every image; default PC_IP:FEED_PORT from mainline/tools/site.conf,
# else 192.168.200.104:8000).
# local.conf and bblayers.conf are written only if they do not exist yet.
#
# Everything heavy lives in $Y (ext4 inside WSL, ~50 GB after a full build). Only the layer
# meta-antminer is read from the repository.
set -euo pipefail

Y="${Y:-$HOME/antminer/yocto}"
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
# default feed address: PC_IP / FEED_PORT from tools/site.conf (+ site.local.conf)
site() { cat "$REPO/mainline/tools/site.conf" "$REPO/mainline/tools/site.local.conf" 2>/dev/null | sed -n "s/^$1=//p" | tail -n 1 | tr -d '\r'; }
SITE_IP=$(site PC_IP); SITE_PORT=$(site FEED_PORT)
LAYER="$REPO/mainline/yocto/meta-antminer"
KVER=6.12.112
FEED_HOST="${FEED_HOST:-${SITE_IP:-192.168.200.104}:${SITE_PORT:-8000}}"   # PC that will serve tmp/deploy/ipk over HTTP

if ! dpkg -s chrpath >/dev/null 2>&1 || ! dpkg -s zstd >/dev/null 2>&1; then
    echo ">> installing Yocto host packages (needs sudo; or run this block as root: wsl -u root)"
    sudo apt-get update
    sudo apt-get install -y build-essential chrpath cpio debianutils diffstat file gawk gcc git \
        iputils-ping libacl1 liblz4-tool lz4 locales python3 python3-git python3-jinja2 python3-pexpect \
        python3-pip python3-subunit socat texinfo unzip wget xz-utils zstd
    sudo locale-gen en_US.UTF-8 >/dev/null || true
fi
# Ubuntu 24.04 (non-WSL kernels) blocks unprivileged user namespaces, which bitbake needs.
# Only try when sudo works without a password prompt (non-interactive runs would hang otherwise).
if [ -e /proc/sys/kernel/apparmor_restrict_unprivileged_userns ] && sudo -n true 2>/dev/null; then
    sudo -n sysctl -w kernel.apparmor_restrict_unprivileged_userns=0 >/dev/null 2>&1 || true
fi

mkdir -p "$Y/downloads" "$Y/sstate-cache"
cd "$Y"
[ -d poky ] || git clone -b scarthgap --depth 1 https://git.yoctoproject.org/poky poky
[ -d meta-openembedded ] || git clone -b scarthgap --depth 1 https://git.openembedded.org/meta-openembedded meta-openembedded

echo ">> kernel tarball + checksum into the recipe"
wget -c -q -P downloads "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-$KVER.tar.xz"
SHA=$(sha256sum "downloads/linux-$KVER.tar.xz" | cut -d' ' -f1)
RECIPE="$LAYER/recipes-kernel/linux/linux-antminer_6.12.bb"
if grep -q '@SHA256@' "$RECIPE"; then sed -i "s/@SHA256@/$SHA/" "$RECIPE"; fi
echo "   linux-$KVER.tar.xz sha256 $SHA"

mkdir -p build/conf
if [ ! -f build/conf/bblayers.conf ]; then
cat > build/conf/bblayers.conf <<EOF
POKY_BBLAYERS_CONF_VERSION = "2"
BBPATH = "\${TOPDIR}"
BBFILES ?= ""
BBLAYERS ?= " \\
  $Y/poky/meta \\
  $Y/poky/meta-poky \\
  $Y/meta-openembedded/meta-oe \\
  $Y/meta-openembedded/meta-python \\
  $LAYER \\
  "
EOF
fi
if [ ! -f build/conf/local.conf ]; then
cat > build/conf/local.conf <<EOF
MACHINE = "antminer-bbb"
DISTRO = "antminer"
PACKAGE_CLASSES = "package_ipk"
DL_DIR = "$Y/downloads"
SSTATE_DIR = "$Y/sstate-cache"
TMPDIR = "$Y/build/tmp"

# opkg feed baked into /etc/opkg of the image (served from the PC, see serve-feed.ps1)
PACKAGE_FEED_URIS = "http://$FEED_HOST"
PACKAGE_FEED_BASE_PATHS = "ipk"
PACKAGE_FEED_ARCHS = "all cortexa8hf-neon antminer_bbb"

BB_DISKMON_DIRS ??= "\\
    STOPTASKS,\${TMPDIR},1G,100K \\
    STOPTASKS,\${DL_DIR},1G,100K \\
    STOPTASKS,\${SSTATE_DIR},1G,100K \\
    HALT,\${TMPDIR},100M,1K \\
    HALT,\${DL_DIR},100M,1K \\
    HALT,\${SSTATE_DIR},100M,1K"
CONF_VERSION = "2"
EOF
fi

if [ "${1:-}" = "setup" ]; then echo ">> setup done, no build"; exit 0; fi

echo ">> setup done; starting the build (same as: bash build.sh${1:+ $1})"
exec bash "$REPO/mainline/yocto/build.sh" "${1:-}"
