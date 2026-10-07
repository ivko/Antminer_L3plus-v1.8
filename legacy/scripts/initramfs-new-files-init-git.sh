#!/bin/bash
set -e
opkg update && opkg install git
git config --global http.sslCAinfo /etc/ssl/certs/ca-certificates.crt
cd / && git init && git add bin etc home lib sbin usr var www
# Create a list of files to remove from the initramfs 

# # Create a tarball of the files to add
# tar -czvf /new-files.tgz $(git status -s | sed -r "s/..(.*)/\1 /")