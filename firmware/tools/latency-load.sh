#!/bin/sh
# Reproducible background load for the latency measurements (docs/10-latency.md, "under load").
#   latency-load.sh start [cpu] [nand] [net]   # default: all three
#       cpu : 2 busy shells at normal priority
#       nand: UBIFS write/delete loop (16 MB files) on /data
#       net : UDP receiver on port 9; run tools/latency-flood.py <board> on the PC as the sender
#   latency-load.sh stop
#   latency-load.sh status
cmd=$1; shift
case "$cmd" in
start)
    [ $# -eq 0 ] && set -- cpu nand net
    for what in "$@"; do
        case $what in
        cpu)  for i in 1 2; do nohup sh -c 'while :; do :; done' >/dev/null 2>&1 & done ;;
        nand) nohup sh -c 'while :; do dd if=/dev/zero of=/data/.loadtest bs=1M count=16 conv=fsync 2>/dev/null; rm -f /data/.loadtest; done' >/dev/null 2>&1 & ;;
        net)  nohup sh -c 'while :; do nc -u -l -p 9 >/dev/null 2>&1 || sleep 1; done' >/dev/null 2>&1 & ;;
        *) echo "unknown load: $what"; exit 1 ;;
        esac
    done
    sleep 3; echo "load: $*"; cat /proc/loadavg ;;
stop)
    for p in $(ps | grep -E 'while :|nc -u -l' | grep -v grep | awk '{print $1}'); do kill $p 2>/dev/null; done
    sleep 1; rm -f /data/.loadtest; cat /proc/loadavg ;;
status)
    ps | grep -E 'while :|nc -u -l|latency-echo' | grep -v grep; cat /proc/loadavg
    grep -E 'eth0' /proc/net/dev | awk '{print "eth0 rx packets", $3, "tx packets", $11}' ;;
*) echo "usage: $0 start [cpu|nand|net ...] | stop | status"; exit 1 ;;
esac
