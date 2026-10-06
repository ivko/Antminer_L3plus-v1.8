SUMMARY = "Board glue for the Antminer BB-Black V1.8 I/O module"
DESCRIPTION = "Early boot: volatile dirs + hardware watchdog feeder (no reset button on this \
board). Config: per-board hostname from /config or the MAC address, persistent dirs on /config, \
fstab entries for the NAND partitions."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://antminer-early.init file://antminer-config.init file://fstab.append file://volatiles"

S = "${WORKDIR}"

inherit update-rc.d allarch

PACKAGES =+ "${PN}-config"
INITSCRIPT_PACKAGES = "${PN} ${PN}-config"
# after mountall.sh (S03, re-mounts the /var/volatile tmpfs) and before populate-volatile.sh (S37);
# from here on a hung userspace reboots the board within 60 s
INITSCRIPT_NAME:${PN} = "antminer-early"
INITSCRIPT_PARAMS:${PN} = "start 36 S ."
# after hostname.sh (S39) and hwclock (S40), before networking (rc5.d S01) and dropbear (S10)
INITSCRIPT_NAME:${PN}-config = "antminer-config"
INITSCRIPT_PARAMS:${PN}-config = "start 41 S ."

RDEPENDS:${PN} = "busybox ${PN}-config"
RDEPENDS:${PN}-config = "busybox"

do_install() {
    install -d ${D}${sysconfdir}/init.d
    install -m 0755 ${WORKDIR}/antminer-early.init ${D}${sysconfdir}/init.d/antminer-early
    install -m 0755 ${WORKDIR}/antminer-config.init ${D}${sysconfdir}/init.d/antminer-config
    install -m 0644 ${WORKDIR}/fstab.append ${D}${sysconfdir}/fstab.antminer
    install -d ${D}/config ${D}/data
    # a second volatiles file also silences poky's populate-volatile.sh, which errors out
    # (grep/sed/rm on a never-created temp file) when 00_core is the only config file
    install -d ${D}${sysconfdir}/default/volatiles
    install -m 0644 ${WORKDIR}/volatiles ${D}${sysconfdir}/default/volatiles/50_antminer
}

# append our mount points to the fstab that base-files ships (runs at rootfs build time, $D set)
pkg_postinst:${PN}() {
    grep -q '^/dev/mtdblock9' $D${sysconfdir}/fstab || cat $D${sysconfdir}/fstab.antminer >> $D${sysconfdir}/fstab
}

FILES:${PN} = "${sysconfdir}/init.d/antminer-early ${sysconfdir}/fstab.antminer ${sysconfdir}/default/volatiles/50_antminer /config /data"
FILES:${PN}-config = "${sysconfdir}/init.d/antminer-config"
