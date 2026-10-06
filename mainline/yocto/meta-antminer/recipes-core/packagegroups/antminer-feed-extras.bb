SUMMARY = "Packages built for the opkg feed but not installed in the base initramfs"
DESCRIPTION = "Heavier software for boards that use the UBIFS data overlay: OpenPLC runtime \
with the on-target toolchain it needs, Python, debugging tools. 'bitbake antminer-feed-extras' \
builds them all into tmp/deploy/ipk."
LICENSE = "MIT"

inherit packagegroup

# libmodbus-dev is wanted on purpose: OpenPLC compiles programs on the target
INSANE_SKIP:${PN} += "dev-deps"

RDEPENDS:${PN} = " \
    openplc-runtime \
    matiec \
    gcc gcc-symlinks g++ g++-symlinks cpp cpp-symlinks binutils binutils-symlinks make \
    libc6-dev libstdc++-dev \
    python3 python3-modules \
    libmodbus-dev libgpiod-dev \
    bash \
    strace ldd \
    "
