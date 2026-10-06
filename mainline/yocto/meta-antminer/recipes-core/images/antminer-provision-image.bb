SUMMARY = "Antminer provisioning system: rootfs of the microSD card (partition 2) + the whole card image"
DESCRIPTION = "Boots from the card with the standard kernel/initramfs (antminer.root=sd) and offers \
a web UI (port 80) to flash NAND, build per-board device trees from YAML and configure services. \
IMAGE_FSTYPES ext4 + wic: the .wic is the complete card (boot FAT with MLO/u-boot/uEnv/kernel/DTBs/ \
initramfs + this rootfs)."
LICENSE = "MIT"

inherit core-image

IMAGE_FEATURES += "ssh-server-dropbear debug-tweaks package-management"

CORE_IMAGE_EXTRA_INSTALL = " \
    init-ifupdown os-release \
    antminer-base antminer-pinmux antminer-web antminer-provision \
    libgpiod libgpiod-tools i2c-tools \
    mtd-utils mtd-utils-ubifs mtd-utils-jffs2 \
    dtc python3-core python3-json python3-pyyaml \
    e2fsprogs-mke2fs e2fsprogs-e2fsck dosfstools \
    "

IMAGE_LINGUAS = ""
IMAGE_ROOTFS_MAXSIZE = ""
IMAGE_FSTYPES = "ext4 wic"
# found via the layer's wic/ directory (BBPATH)
WKS_FILE = "antminer-sd.wks"

# files of the FAT boot partition: Bitmain bootloader + our kernel, DTBs and the standard initramfs
IMAGE_BOOT_FILES = " \
    MLO u-boot.img uEnv-sd.txt;uEnv.txt \
    uImage am335x-antminer.dtb \
    antminer-image-antminer-bbb.rootfs.cpio.gz.u-boot;initramfs.cpio.gz.u-boot \
    "
do_image_wic[depends] += "antminer-sd-boot:do_deploy virtual/kernel:do_deploy antminer-image:do_image_complete"
