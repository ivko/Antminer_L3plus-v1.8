SUMMARY = "MatIEC IEC 61131-3 compiler (iec2c), the fork bundled with OpenPLC_v3"
HOMEPAGE = "https://github.com/thiagoralves/OpenPLC_v3"
LICENSE = "GPL-3.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-3.0-only;md5=c79ff39f19dfec6d293b95dea7b07891"

SRC_URI = "git://github.com/thiagoralves/OpenPLC_v3.git;protocol=https;branch=master"
SRCREV = "b5d41356dab4aeadca0dd7ca64ba542f870b595d"
PV = "0.1+git"

S = "${WORKDIR}/git/utils/matiec_src"

DEPENDS = "flex-native bison-native"

inherit autotools

# OpenPLC runs ./iec2c from /opt/openplc/webserver and expects the standard library
# in ./lib next to it (shipped by openplc-runtime). A real copy, not a symlink: iec2c
# derives its default library directory from the executable's location.
do_install:append() {
    install -d ${D}/opt/openplc/webserver
    install -m 0755 ${D}${bindir}/iec2c ${D}/opt/openplc/webserver/iec2c
}

FILES:${PN} += "/opt/openplc/webserver/iec2c"
