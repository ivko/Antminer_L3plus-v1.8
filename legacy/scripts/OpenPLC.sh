# OpenPLC

export OPENPLC_DIR="$PWD"
export VENV_DIR="$OPENPLC_DIR/.venv"
./start_openplc.sh

webserver/core# 
g++ -std=gnu++11 -I ./lib -c Config0.c -lasiodnp3 -lasiopal -lopendnp3 -lopenpal -w
g++ -std=gnu++11 -I ./lib -c Res0.c -lasiodnp3 -lasiopal -lopendnp3 -lopenpal -w
g++ -std=gnu++11 *.cpp *.o -o openplc -I ./lib -pthread -fpermissive -I/usr/local/include/modbus -L/usr/local/lib -lmodbus -lasiodnp3 -lasiopal -lopendnp3 -lopenpal -w


# pkg-config https://github.com/openwrt/packages/blob/openwrt-22.03/devel/pkg-config/Makefile 
# https://pkg-config.freedesktop.org/releases/

# http://feeds.angstrom-distribution.org/feeds/v2014.06/ipk/eglibc/armv7at2hf-vfp-neon/machine/beaglebone/angstrom-feed-configs_v2014.06-r17.8_beaglebone.ipk
opkg update
opkg install update-alternatives ca-certificates wget git autoconf automake libtool gcc-dev gcc-symlinks cpp-symlinks g++-symlinks binutils binutils-symlinks make tar bison-dev flex-dev bash cmake
echo ca_certificate=/etc/ssl/certs/ca-certificates.crt > ~/.wgetrc
git config --global http.sslCAinfo /etc/ssl/certs/ca-certificates.crt


mount /dev/mmcblk0p2 /mnt/card
cd /mnt/card/
git clone https://github.com/thiagoralves/OpenPLC_v3.git
cd OpenPLC_v3


# v2015.12 - g++ 5.2.0

killall monitor-ipsig
killall monitor-recobtn
opkg remove lighttpd
opkg remove lighttpd* cgminer-l3p minermonitor monitor-ipsig monitor-recobtn
opkg remove angstrom-feed-configs



opkg install http://feeds.angstrom-distribution.org/feeds/v2015.12/ipk/glibc/armv7at2hf-vfp-neon/machine/beaglebone/angstrom-feed-configs_1.0-r16.4_beaglebone.ipk
opkg update
opkg remove libthread-db1
opkg install update-alternatives ca-certificates wget git libtool gcc-dev gcc-symlinks cpp-symlinks g++-symlinks binutils-symlinks make cmake tar bash

mount /dev/mmcblk0p2 /mnt/card
cd /mnt/card/
cd OpenPLC_v3/utils/dnp3_src/
make install

#load from sd card
killall monitor-ipsig
killall monitor-recobtn
killall ntpd
killall syslogd
killall klogd
opkg remove lighttpd
opkg remove lighttpd* cgminer-l3p minermonitor monitor-ipsig monitor-recobtn
mount --bind /config/root/usr /usr
mount --bind /config/root/lib /lib
mount --bind /config/root/bin /bin
mount --bind /config/root/sbin /sbin
mount --bind /config/root/var /var
mount --bind /config/root/etc /etc
mount /dev/mmcblk0p2 /mnt/card
swapon /mnt/card/swapfile





#openssl https://docs.oracle.com/en/java/javacard/3.2/jcdksu/example-build-openssl-3-32-bit-ubuntu-linux-20.04.4-lts.html
perl ./Configure linux-armv4  no-tests --prefix=/usr --openssldir=/usr/share/ssl
make
make install_sw install_ssldirs
tar -czvf openssl_1.1.1v.tar.gz /usr/lib/libcrypto.so.1.1 /usr/lib/libssl.so.1.1 /usr/lib/libcrypto.so /usr/lib/libssl.so /usr/bin/openssl /usr/bin/c_rehash /usr/share/ssl/misc/CA.pl /usr/share/ssl/misc/tsget.pl /usr/share/ssl/misc/tsget /usr/share/ssl/openssl.cnf.dist /usr/share/ssl/ct_log_list.cnf.dist /usr/lib/engines-1.1/capi.so /usr/lib/engines-1.1/padlock.so
tar -czvf openssl-dev_1.1.1v.tar.gz /usr/include/openssl/* /usr/lib/libcrypto.a /usr/lib/libssl.a /usr/lib/pkgconfig/libcrypto.pc /usr/lib/pkgconfig/libssl.pc /usr/lib/pkgconfig/openssl.pc




#Python 3.11 https://docs.posit.co/resources/install-python-source/#download-and-extract-python
LIBFFI_INCLUDEDIR=/usr/lib/libffi-3.2.1/include
export PYTHON_VERSION=3.11.8
export PYTHON_MAJOR=3
./configure \
    --prefix=/usr/ \
    --disable-test-modules \
    --without-doc-strings \
    --enable-optimizations \
    --disable-ipv6 \
    --with-openssl=/usr/lib/ssl \
    --with-openssl-rpath=auto \
    --with-pkg-config=no \
    --without-static-libpython \
    --with-system-ffi \
    LDFLAGS=-Wl,-rpath=/usr/lib,--disable-new-dtags

######################
# try to build
tar -xvf /mnt/card/root/usr.tar.gz usr/local
cp usr/local/lib/libmodbus.* /usr/local/lib/
cp -r /tmp/usr/local/include/modbus /usr/local/include/



