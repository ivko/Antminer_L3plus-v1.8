dtc am3352-antminer-next.dts -O dtb -o am3352-antminer-next.dtb
flash_erase /dev/mtd6 0x0 0x1
nandwrite -p /dev/mtd6 am3352-antminer-next.dtb