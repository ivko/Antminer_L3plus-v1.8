# Antminer_L3plus-v1.8
Linux version 3.8.13 (xxl@armdev01) (gcc version 4.7.4 20130626 (prerelease) (Linaro GCC 4.7-2013.07) ) #22 SMP Tue Dec 2 15:26:11 CST 2014

## Tasks
- Make a new flasher image with following requirements:
  - Make the size smaller by removing unused software on it
  - Make it interactive:
    - ask to approve flashing the coresponding nand
    - ask to choose what source to be flashed by listing avalable sources indexed by number for each section of the nand, u-boot, uImage, dtb
- Add dts source files from https://github.com/derekmolloy/boneDeviceTree/blob/master/DTSource3.8.13
- Make a repo with "new-files" to save space in the repo. Leave just one .SD image file as a source (initramfs.bin.SD-fixed)
- Make one dtd with uart1 enabled and all GPIOs enabled (testing libmodbus).
- Build libmodbus.apk with required dependencies.
