SUMMARY = "Web UI for provisioning and configuring the Antminer I/O module (Flask, port 80)"
DESCRIPTION = "NAND flashing with verification, YAML pinmux profiles compiled to DTBs on the board, \
hostname/network/NTP/SSH settings on /config, data partition management, logs. Thin layer over \
antminer-flash-nand, antminer-dtb and antminer-data. No authentication: meant for the provisioning \
SD card; on a NAND system put it behind your own access control."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

FILESEXTRAPATHS:prepend := "${ANTMINER_MAINLINE_DIR}/web:${THISDIR}/files:"
SRC_URI = "file://run.py file://antminer_web file://antminer-web.init"

S = "${WORKDIR}"
inherit update-rc.d allarch

INITSCRIPT_NAME = "antminer-web"
INITSCRIPT_PARAMS = "start 50 5 . stop 15 0 1 6 ."

WEB_DIR = "${datadir}/antminer/web"

do_install() {
    install -d ${D}${WEB_DIR} ${D}${sysconfdir}/init.d
    install -m 0755 ${WORKDIR}/run.py ${D}${WEB_DIR}/run.py
    cp -r ${WORKDIR}/antminer_web ${D}${WEB_DIR}/
    rm -rf ${D}${WEB_DIR}/antminer_web/__pycache__
    install -m 0755 ${WORKDIR}/antminer-web.init ${D}${sysconfdir}/init.d/antminer-web
}

FILES:${PN} = "${WEB_DIR} ${sysconfdir}/init.d/antminer-web"
RDEPENDS:${PN} = "python3-core python3-flask python3-json python3-threading python3-logging python3-netserver \
                  python3-pyyaml antminer-pinmux antminer-base dtc mtd-utils busybox"
