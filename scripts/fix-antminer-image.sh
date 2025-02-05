#!/bin/sh
echo "#!/bin/sh
while sleep 999999999; do :; done" > /sbin/monitorcg
/etc/init.d/cgminer.sh stop
killall monitorcg

# Opkg update
opkg install http://feeds.angstrom-distribution.org/feeds/v2013.06/ipk/eglibc/armv7ahf-vfp-neon/machine/beaglebone/angstrom-feed-configs_v2013.06-r17.2_beaglebone.ipk
opkg update

# ca-certificates
opkg install update-alternatives ca-certificates wget
echo ca_certificate=/etc/ssl/certs/ca-certificates.crt > ~/.wgetrc

# Start dropbear and stop cgminer
echo NO_START=0 > /etc/default/dropbear
/etc/init.d/dropbear start
/etc/init.d/cgminer.sh stop

# DTC utility
opkg install dtc dtc-dev

