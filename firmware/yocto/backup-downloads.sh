#!/bin/bash
# Mirror the Yocto source downloads out of WSL (or restore them into a new build tree).
#
#   bash backup-downloads.sh                 # ~/antminer/yocto/downloads -> <repo>/../backup/yocto-downloads
#   bash backup-downloads.sh restore         # the other way, before setup-yocto.sh on a new machine
#   BACKUP=/mnt/d/x bash backup-downloads.sh
#
# With these files every recipe builds without internet and without depending on upstream
# servers still existing (kernel tarball, OpenPLC git, PyPI tarballs, ...). ~2 GB.
set -euo pipefail
Y="${Y:-$HOME/antminer/yocto}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
# default: a "backup" folder next to the repository (E:\Antminer\backup for E:\Antminer\repo)
BACKUP="${BACKUP:-$(dirname "$REPO")/backup/yocto-downloads}"
mkdir -p "$BACKUP" "$Y/downloads"
if [ "${1:-}" = "restore" ]; then
    rsync -a --info=stats1 "$BACKUP/" "$Y/downloads/"
else
    # *.done / *.lock are bitbake bookkeeping, regenerated as needed
    rsync -a --delete --info=stats1 --exclude '*.lock' "$Y/downloads/" "$BACKUP/"
fi
du -sh "$BACKUP"
