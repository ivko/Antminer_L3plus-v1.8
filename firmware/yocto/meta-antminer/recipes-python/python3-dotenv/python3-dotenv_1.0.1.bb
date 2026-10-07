SUMMARY = "Read key-value pairs from a .env file and set them as environment variables"
HOMEPAGE = "https://github.com/theskumar/python-dotenv"
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/BSD-3-Clause;md5=550794465ba0ec5312d6919e203a55f9"

PYPI_PACKAGE = "python-dotenv"
SRC_URI[sha256sum] = "e324ee90a023d808f1959c46bcbc04446a10ced277783dc6ee09987c37ec10ca"

inherit pypi setuptools3

RDEPENDS:${PN} = "python3-core python3-io python3-shell"
