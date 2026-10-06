#!/bin/bash
# (Re)start or watch the Yocto build inside WSL.
#   bash build.sh            # start "bitbake antminer-image && bitbake package-index" in the background
#   bash build.sh fg         # same, foreground
#   bash build.sh status     # last lines of the log + running tasks
#   bash build.sh <target>   # e.g. "bash build.sh linux-antminer -c menuconfig" (foreground)
set -euo pipefail
Y="${Y:-$HOME/antminer/yocto}"
LOG="$Y/build/bitbake.log"
cd "$Y"
# shellcheck disable=SC1091
set +u; source poky/oe-init-build-env build >/dev/null; set -u

case "${1:-}" in
    status)
        if pgrep -f 'bin/bitbake ' >/dev/null; then echo "bitbake: RUNNING"; else echo "bitbake: not running"; fi
        tail -n 20 "$LOG" 2>/dev/null
        ;;
    fg)
        bitbake antminer-image antminer-feed-image && bitbake package-index
        ;;
    "")
        if pgrep -f 'bin/bitbake ' >/dev/null; then echo "a bitbake is already running"; exit 0; fi
        # antminer-feed-image exists only to get the feed packages written as ipk (see its recipe)
        nohup bash -c "bitbake antminer-image antminer-feed-image && bitbake package-index; echo BITBAKE_EXIT=\$?" > "$LOG" 2>&1 &
        echo "started in background, pid $!, log $LOG"
        ;;
    *)
        bitbake "$@"
        ;;
esac
