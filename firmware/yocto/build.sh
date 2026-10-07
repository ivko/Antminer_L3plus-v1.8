#!/bin/bash
# Build everything (or one target) inside WSL. Run from anywhere.
#
#   bash build.sh            # full build in the background, log: ~/antminer/yocto/build/bitbake.log
#   bash build.sh fg         # full build in the foreground
#   bash build.sh status     # is bitbake running + last log lines
#   bash build.sh <args>     # any bitbake command line, foreground, e.g.
#                            #   bash build.sh antminer-provision-image
#                            #   bash build.sh linux-antminer -c menuconfig
#
# "Full build" = the three images + the opkg feed index:
#   antminer-image            initramfs for NAND (mtd8) + uImage + DTB
#   antminer-provision-image  complete provisioning SD card (.wic)
#   antminer-feed-image       makes bitbake write the ipk files of the feed packages (OpenPLC...)
#   package-index             Packages.gz files so opkg on the boards sees the feed
set -euo pipefail
Y="${Y:-$HOME/antminer/yocto}"
LOG="$Y/build/bitbake.log"
TARGETS="antminer-image antminer-provision-image antminer-feed-image"
cd "$Y"
# shellcheck disable=SC1091
set +u; source poky/oe-init-build-env build >/dev/null; set -u

case "${1:-}" in
    status)
        if pgrep -f 'bin/bitbake ' >/dev/null; then echo "bitbake: RUNNING"; else echo "bitbake: not running"; fi
        tail -n 20 "$LOG" 2>/dev/null
        ;;
    fg)
        bitbake $TARGETS && bitbake package-index
        ;;
    "")
        if pgrep -f 'bin/bitbake ' >/dev/null; then echo "a bitbake is already running"; exit 0; fi
        nohup bash -c "bitbake $TARGETS && bitbake package-index; echo BITBAKE_EXIT=\$?" > "$LOG" 2>&1 &
        echo "started in background (pid $!), log: $LOG"
        echo "watch: bash $(readlink -f "$0") status"
        ;;
    *)
        bitbake "$@"
        ;;
esac
