SUMMARY = "Throw-away image whose only purpose is to get every feed package built and written as ipk"
DESCRIPTION = "bitbake of a packagegroup compiles its runtime dependencies but does not write their \
ipk files; an image does. This image is never flashed. Its rootfs (tar.gz) can be ignored."
LICENSE = "MIT"

inherit core-image

IMAGE_FEATURES = "package-management"
IMAGE_INSTALL = "packagegroup-core-boot antminer-feed-extras"
IMAGE_FSTYPES = "tar.gz"
IMAGE_LINGUAS = ""
