SUMMARY = "Modbus protocol stack in Python, 2.x API as used by OpenPLC_v3 (pymodbus.client.sync)"
HOMEPAGE = "https://github.com/riptideio/pymodbus"
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/BSD-3-Clause;md5=550794465ba0ec5312d6919e203a55f9"

SRC_URI[sha256sum] = "5ef68c1a109bdb467c830ef003ef2db6494349a5248e4af946fe21c9eefe7e74"

inherit pypi setuptools3

# setup.py imports pymodbus.utilities -> six at build time
DEPENDS += "python3-six-native"

RDEPENDS:${PN} = "python3-core python3-six python3-pyserial python3-logging python3-netclient python3-threading"
