SUMMARY = "Glue for the provisioning SD card system: /boot mount, banner with the web UI address"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://antminer-provision.init file://fstab-boot"
S = "${WORKDIR}"
inherit update-rc.d allarch

INITSCRIPT_NAME = "antminer-provision"
# after networking (S01) and dropbear (S10), before the web UI (S50): mount /boot, print the URL
INITSCRIPT_PARAMS = "start 20 5 . stop 20 0 1 6 ."

do_install() {
    install -d ${D}${sysconfdir}/init.d ${D}/boot
    install -m 0755 ${WORKDIR}/antminer-provision.init ${D}${sysconfdir}/init.d/antminer-provision
    install -m 0644 ${WORKDIR}/fstab-boot ${D}${sysconfdir}/fstab.boot
}

pkg_postinst:${PN}() {
    grep -q '^/dev/mmcblk0p1' $D${sysconfdir}/fstab || cat $D${sysconfdir}/fstab.boot >> $D${sysconfdir}/fstab
}

FILES:${PN} = "${sysconfdir}/init.d/antminer-provision ${sysconfdir}/fstab.boot /boot"
RDEPENDS:${PN} = "busybox"
