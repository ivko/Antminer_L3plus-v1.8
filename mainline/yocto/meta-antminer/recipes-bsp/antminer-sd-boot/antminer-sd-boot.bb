SUMMARY = "Boot files for the provisioning microSD card (Bitmain MLO/u-boot.img + uEnv.txt)"
DESCRIPTION = "The stock Bitmain U-Boot 2013.04 binaries (so boards whose SYSBOOT puts MMC0 \
first boot from the card too) and the uEnv.txt that makes that U-Boot load our kernel, DTB and \
initramfs from the card with antminer.root=sd. Deployed to DEPLOY_DIR_IMAGE for the wic image."
LICENSE = "GPL-2.0-or-later"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-or-later;md5=fed54355545ffd980b814dab4a3b312c"

FILESEXTRAPATHS:prepend := "${ANTMINER_MAINLINE_DIR}/boot/bitmain:${ANTMINER_MAINLINE_DIR}/sdcard:"
SRC_URI = "file://MLO file://u-boot.img file://uEnv-sd.txt"

S = "${WORKDIR}"
inherit deploy nopackages
PACKAGE_ARCH = "${MACHINE_ARCH}"
COMPATIBLE_MACHINE = "antminer-bbb"

do_configure[noexec] = "1"
do_compile[noexec] = "1"
do_install[noexec] = "1"

do_deploy() {
    install -m 0644 ${WORKDIR}/MLO ${DEPLOYDIR}/MLO
    install -m 0644 ${WORKDIR}/u-boot.img ${DEPLOYDIR}/u-boot.img
    install -m 0644 ${WORKDIR}/uEnv-sd.txt ${DEPLOYDIR}/uEnv-sd.txt
}
addtask deploy after do_install before do_build
