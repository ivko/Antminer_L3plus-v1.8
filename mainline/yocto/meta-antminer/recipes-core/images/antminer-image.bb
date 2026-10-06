SUMMARY = "Antminer BB-Black V1.8 I/O module - initramfs for the NAND root partition (20 MiB)"
LICENSE = "MIT"

inherit core-image

# debug-tweaks: empty root password, root ssh login. Replace with a real password before deployment.
IMAGE_FEATURES += "package-management ssh-server-dropbear debug-tweaks"

CORE_IMAGE_EXTRA_INSTALL = " \
    init-ifupdown os-release \
    antminer-base \
    libgpiod libgpiod-tools \
    libmodbus \
    mtd-utils mtd-utils-ubifs mtd-utils-jffs2 \
    i2c-tools \
    "

IMAGE_LINGUAS = ""
# cpio: no size padding needed, but fail the build if the compressed initramfs would not fit mtd8
IMAGE_ROOTFS_MAXSIZE = ""

python do_check_initramfs_size() {
    import os
    img = os.path.join(d.getVar('IMGDEPLOYDIR'), d.getVar('IMAGE_NAME') + '.rootfs.cpio.gz.u-boot')
    if not os.path.exists(img):
        img = os.path.join(d.getVar('IMGDEPLOYDIR'), d.getVar('IMAGE_NAME') + '.cpio.gz.u-boot')
    if os.path.exists(img):
        size = os.path.getsize(img)
        limit = 0x1400000
        bb.plain("antminer-image: %s is %d bytes, NAND root partition limit %d bytes (margin %d)" % (os.path.basename(img), size, limit, limit - size))
        if size > limit:
            bb.fatal("initramfs does not fit the 20 MiB NAND root partition")
}
addtask check_initramfs_size after do_image_complete before do_build
