SUMMARY = "Mainline stable Linux for the Antminer BB-Black V1.8 (AM3352)"
DESCRIPTION = "linux-stable 6.12.y with the board DTS and the slim AM33xx-only defconfig \
from repo/firmware (same files as build-kernel.sh)."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://COPYING;md5=6bc538ed5bd9a7fc9398086aedcd7e46"

inherit kernel

PV = "6.12.112"
LINUX_VERSION = "${PV}"
LINUX_VERSION_EXTENSION = "-antminer"

# PREEMPT_RT (decided 2026-11-03, measurements in docs/10-latency.md). Mainline 6.12 has no
# ARCH_SUPPORTS_RT for 32-bit ARM; the external rt patch adds it. kernel/defconfig has
# CONFIG_PREEMPT_RT=y, which only takes effect with this patch applied. When PV moves, take the
# matching patch from https://cdn.kernel.org/pub/linux/kernel/projects/rt/6.12/ (an rt patch one
# stable release behind, as here, applied cleanly).
RT_PATCH = "patch-6.12.111-rt21.patch.xz"

# dts/ and kernel/ of repo/firmware are searched first for file:// entries
FILESEXTRAPATHS:prepend := "${ANTMINER_FIRMWARE_DIR}/kernel:${ANTMINER_FIRMWARE_DIR}/dts:"

SRC_URI = "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-${PV}.tar.xz \
           https://cdn.kernel.org/pub/linux/kernel/projects/rt/6.12/${RT_PATCH};name=rt \
           file://defconfig \
           file://am335x-antminer.dts \
           file://am335x-antminer-base.dtsi \
           "
SRC_URI[sha256sum] = "164dc9d1f6c93c61a15e1f071c48379b467f2b17c469cce7223471968208ed03"
SRC_URI[rt.sha256sum] = "8b9b7b59f0372e1e70b5fd99729765d335928ef0a0196fb1e869afc45fc69b55"

# fail the build instead of silently shipping a non-RT kernel (e.g. patch dropped, defconfig edited)
do_configure:append() {
    grep -q '^CONFIG_PREEMPT_RT=y' ${B}/.config || bbfatal "CONFIG_PREEMPT_RT is not set in the kernel config"
}

S = "${WORKDIR}/linux-${PV}"
COMPATIBLE_MACHINE = "antminer-bbb"

KERNEL_DTS_DIR = "${S}/arch/arm/boot/dts/ti/omap"

do_configure:prepend() {
    cp "${WORKDIR}/am335x-antminer.dts" "${WORKDIR}/am335x-antminer-base.dtsi" "${KERNEL_DTS_DIR}/"
    if ! grep -q 'am335x-antminer.dtb' "${KERNEL_DTS_DIR}/Makefile"; then
        printf '\ndtb-$(CONFIG_SOC_AM33XX) += am335x-antminer.dtb\n' >> "${KERNEL_DTS_DIR}/Makefile"
    fi
}
