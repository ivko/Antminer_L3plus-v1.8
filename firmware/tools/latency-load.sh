#!/bin/sh
# Reproducible background load for the latency measurements (docs/10-latency.md, "under load"):
#   latency-load.sh start   # 2 CPU hogs (normal priority), a UBIFS write/delete loop on /data,
#                           # and a local network receiver; run tools/latency-flood.py on the PC too
#   latency-load.sh stop
#   latency-load.sh status
case "$1" in
start)
    for i in 1 2; do nohup sh -c 'while :; do :; done' >/dev/null 2>&1 & done
    nohup sh -c 'while :; do dd if=/dev/zero of=/data/.loadtest bs=1M count=16 conv=fsync 2>/dev/null; rm -f /data/.loadtest; done' >/dev/null 2>&1 &
    # answer the UDP flood from the PC so the network stack does RX + TX work
    nohup sh -c 'while :; do nc -u -l -p 9 >/dev/null 2>&1 || sleep 1; done' >/dev/null 2>&1 &
    sleep 3; cat /proc/loadavg ;;
stop)
    for p in $(ps | grep -E 'while :|nc -u -l' | grep -v grep | awk '{print $1}'); do kill $p 2>/dev/null; done
    sleep 1; rm -f /data/.loadtest; cat /proc/loadavg ;;
status)
    ps | grep -E 'while :|nc -u -l|latency-echo' | grep -v grep; cat /proc/loadavg
    grep -E 'eth0' /proc/net/dev | awk '{print "eth0 rx packets", $3, "tx packets", $11}' ;;
*) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
