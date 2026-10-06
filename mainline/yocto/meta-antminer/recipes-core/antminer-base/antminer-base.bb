SUMMARY = "Board glue for the Antminer BB-Black V1.8 I/O module"
DESCRIPTION = "/init with the optional persistent overlay on the NAND data partition (UBIFS), \
early boot: volatile dirs + hardware watchdog feeder (no reset button on this board), \
config: per-board hostname from /config or the MAC address, persistent dirs on /config, \
fstab entries for the NAND partitions, antminer-data tool."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

FILESEXTRAPATHS:prepend := "${ANTMINER_MAINLINE_DIR}/tools:"
SRC_URI = "file://init.sh \
           file://antminer-data \
           file://flash-nand.sh \
           file://antminer-early.init \
           file://antminer-config.init \
           file://antminer-boot-ok.init \
           file://antminer-ntp.init \
           file://antminer-ntp-hook \
           file://fstab.append \
           file://volatiles \
           file://opkg-antminer.conf \
           "

S = "${WORKDIR}"

inherit update-rc.d allarch

PACKAGES =+ "${PN}-config ${PN}-bootok ${PN}-ntp"
INITSCRIPT_PACKAGES = "${PN} ${PN}-config ${PN}-bootok ${PN}-ntp"
# right after networking (rc5.d S01): the RTC has no battery, the clock starts in 2018
INITSCRIPT_NAME:${PN}-ntp = "antminer-ntp"
INITSCRIPT_PARAMS:${PN}-ntp = "start 05 5 . stop 20 0 1 6 ."
# after mountall.sh (S03, re-mounts the /var/volatile tmpfs) and before populate-volatile.sh (S37);
# from here on a hung userspace reboots the board within 60 s
INITSCRIPT_NAME:${PN} = "antminer-early"
INITSCRIPT_PARAMS:${PN} = "start 36 S ."
# after hostname.sh (S39) and hwclock (S40), before networking (rc5.d S01) and dropbear (S10)
INITSCRIPT_NAME:${PN}-config = "antminer-config"
INITSCRIPT_PARAMS:${PN}-config = "start 41 S ."
# last thing in rc5.d: boot reached the end -> reset the overlay boot-attempt counter
INITSCRIPT_NAME:${PN}-bootok = "antminer-boot-ok"
INITSCRIPT_PARAMS:${PN}-bootok = "start 99 5 ."

RDEPENDS:${PN} = "busybox mtd-utils-ubifs ${PN}-config ${PN}-bootok ${PN}-ntp"
RDEPENDS:${PN}-config = "busybox"
RDEPENDS:${PN}-bootok = "busybox"
RDEPENDS:${PN}-ntp = "busybox busybox-hwclock"

do_install() {
    install -d ${D}${sysconfdir}/init.d ${D}${sbindir} ${D}/config ${D}/data
    # the kernel runs /init from the initramfs before anything else
    install -m 0755 ${WORKDIR}/init.sh ${D}/init
    install -m 0755 ${WORKDIR}/antminer-data ${D}${sbindir}/antminer-data
    # the same NAND provisioning script as tools/flash-nand.sh (TFTP or a local dir such as /boot)
    install -m 0755 ${WORKDIR}/flash-nand.sh ${D}${sbindir}/antminer-flash-nand
    install -m 0755 ${WORKDIR}/antminer-early.init ${D}${sysconfdir}/init.d/antminer-early
    install -m 0755 ${WORKDIR}/antminer-config.init ${D}${sysconfdir}/init.d/antminer-config
    install -m 0755 ${WORKDIR}/antminer-boot-ok.init ${D}${sysconfdir}/init.d/antminer-boot-ok
    install -m 0755 ${WORKDIR}/antminer-ntp.init ${D}${sysconfdir}/init.d/antminer-ntp
    install -m 0755 ${WORKDIR}/antminer-ntp-hook ${D}${sbindir}/antminer-ntp-hook
    install -m 0644 ${WORKDIR}/fstab.append ${D}${sysconfdir}/fstab.antminer
    # a second volatiles file also silences poky's populate-volatile.sh, which errors out
    # (grep/sed/rm on a never-created temp file) when 00_core is the only config file
    install -d ${D}${sysconfdir}/default/volatiles
    install -m 0644 ${WORKDIR}/volatiles ${D}${sysconfdir}/default/volatiles/50_antminer
    install -d ${D}${sysconfdir}/opkg
    install -m 0644 ${WORKDIR}/opkg-antminer.conf ${D}${sysconfdir}/opkg/antminer.conf
}

# append our mount points to the fstab that base-files ships (runs at rootfs build time, $D set)
pkg_postinst:${PN}() {
    grep -q '^/dev/mtdblock9' $D${sysconfdir}/fstab || cat $D${sysconfdir}/fstab.antminer >> $D${sysconfdir}/fstab
}

FILES:${PN} = "/init ${sbindir}/antminer-data ${sbindir}/antminer-flash-nand ${sysconfdir}/init.d/antminer-early ${sysconfdir}/fstab.antminer ${sysconfdir}/default/volatiles/50_antminer ${sysconfdir}/opkg/antminer.conf /config /data"
FILES:${PN}-config = "${sysconfdir}/init.d/antminer-config"
FILES:${PN}-bootok = "${sysconfdir}/init.d/antminer-boot-ok"
FILES:${PN}-ntp = "${sysconfdir}/init.d/antminer-ntp ${sbindir}/antminer-ntp-hook"
