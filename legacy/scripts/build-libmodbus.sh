#!/bin/bash
opkg update
opkg install update-alternatives wget autoconf automake libtool gcc-dev gcc-symlinks cpp-symlinks g++-symlinks binutils make tar
wget --no-check-certificate https://github.com/stephane/libmodbus/releases/download/v3.1.10/libmodbus-3.1.10.tar.gz
tar -xvzf libmodbus-3.1.10.tar.gz
cd libmodbus-3.1.10
./configure --prefix=/usr --sysconfdir=/etc
make && make install

# gcc <name>.c -o <name> -I/usr/include/modbus/ -lmodbus
# gcc test.c -o test -I/usr/include/modbus/ -lmodbus && chmod +x test && ./test