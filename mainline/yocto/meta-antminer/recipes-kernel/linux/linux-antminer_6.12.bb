SUMMARY = "Mainline stable Linux for the Antminer BB-Black V1.8 (AM3352)"
DESCRIPTION = "linux-stable 6.12.y with the board DTS and the slim AM33xx-only defconfig \
from repo/mainline (same files as build-kernel.sh)."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://COPYING;md5=6bc538ed5bd9a7fc9398086aedcd7e46"

inherit kernel

PV = "6.12.112"
LINUX_VERSION = "${PV}"
LINUX_VERSION_EXTENSION = "-antminer"

# dts/ and kernel/ of repo/mainline are searched first for file:// entries
FILESEXTRAPATHS:prepend := "${ANTMINER_MAINLINE_DIR}/kernel:${ANTMINER_MAINLINE_DIR}/dts:"

SRC_URI = "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-${PV}.tar.xz \
           file://defconfig \
           file://am335x-antminer.dts \
           file://am335x-antminer-base.dtsi \
           "
SRC_URI[sha256sum] = "164dc9d1f6c93c61a15e1f071c48379b467f2b17c469cce7223471968208ed03"

S = "${WORKDIR}/linux-${PV}"
COMPATIBLE_MACHINE = "antminer-bbb"

KERNEL_DTS_DIR = "${S}/arch/arm/boot/dts/ti/omap"

do_configure:prepend() {
    cp "${WORKDIR}/am335x-antminer.dts" "${WORKDIR}/am335x-antminer-base.dtsi" "${KERNEL_DTS_DIR}/"
    if ! grep -q 'am335x-antminer.dtb' "${KERNEL_DTS_DIR}/Makefile"; then
        printf '\ndtb-$(CONFIG_SOC_AM33XX) += am335x-antminer.dtb\n' >> "${KERNEL_DTS_DIR}/Makefile"
    fi
}
