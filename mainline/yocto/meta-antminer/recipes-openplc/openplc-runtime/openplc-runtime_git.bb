SUMMARY = "OpenPLC v3 runtime for the Antminer I/O module"
DESCRIPTION = "Web server (Flask, port 8080), PLC core sources and the build scripts that \
compile an uploaded IEC 61131-3 program on the target with g++. Snap7 (Siemens S7) is built \
from the bundled sources; OpenDNP3 is replaced by the dummy (not built for this platform)."
HOMEPAGE = "https://github.com/thiagoralves/OpenPLC_v3"
LICENSE = "GPL-3.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-3.0-only;md5=c79ff39f19dfec6d293b95dea7b07891"

SRC_URI = "git://github.com/thiagoralves/OpenPLC_v3.git;protocol=https;branch=master \
           file://openplc.init \
           file://antminer.cpp \
           "
SRCREV = "b5d41356dab4aeadca0dd7ca64ba542f870b595d"
PV = "3.0+git"

S = "${WORKDIR}/git"

DEPENDS = "libmodbus"

inherit update-rc.d

INITSCRIPT_NAME = "openplc"
INITSCRIPT_PARAMS = "start 90 5 . stop 10 0 1 6 ."

OPENPLC_DIR = "/opt/openplc"

do_compile() {
    # helpers that run on the target during program compilation
    ${CXX} ${CXXFLAGS} ${LDFLAGS} utils/st_optimizer_src/st_optimizer.cpp -o st_optimizer
    ${CXX} ${CXXFLAGS} -std=c++11 ${LDFLAGS} utils/glue_generator_src/glue_generator.cpp -o glue_generator
    # Siemens S7 library the PLC core links against
    rm -rf utils/snap7_src/build/temp utils/snap7_src/build/bin/linux
    oe_runmake -C utils/snap7_src/build/linux all \
        CXX="${CXX}" CC="${CC}" AR="${AR} rcus" \
        CXXFLAGS="${CXXFLAGS} -O3 -fPIC -pedantic" \
        LinkerName="${CXX}" SharedObjectLinkerName="${CXX} -shared -fPIC ${LDFLAGS}"
}

do_install() {
    install -d ${D}${OPENPLC_DIR}
    cp -r ${S}/webserver ${D}${OPENPLC_DIR}/
    install -m 0755 ${B}/st_optimizer ${D}${OPENPLC_DIR}/webserver/st_optimizer
    install -m 0755 ${B}/glue_generator ${D}${OPENPLC_DIR}/webserver/core/glue_generator

    # snap7: the library + the OpenPLC wrapper (oplc_snap7.h declares the snap7 C API itself);
    # compile_program.sh copies ../utils/snap7_src/wrapper/oplc_snap7.* into core/ on every build
    install -d ${D}${libdir} ${D}${OPENPLC_DIR}/utils/snap7_src
    install -m 0755 ${S}/utils/snap7_src/build/bin/linux/libsnap7.so ${D}${libdir}/libsnap7.so
    cp -r ${S}/utils/snap7_src/wrapper ${D}${OPENPLC_DIR}/utils/snap7_src/

    # platform: linux, Antminer GPIO/ADC hardware layer (libgpiod line names I*/Q*), no EtherCAT, DNP3 dummy
    CORE=${D}${OPENPLC_DIR}/webserver/core
    SCRIPTS=${D}${OPENPLC_DIR}/webserver/scripts
    install -m 0644 ${WORKDIR}/antminer.cpp $CORE/hardware_layers/antminer.cpp
    cp $CORE/hardware_layers/antminer.cpp $CORE/hardware_layer.cpp
    echo linux > $SCRIPTS/openplc_platform
    echo blank_linux > $SCRIPTS/openplc_driver
    echo "" > $SCRIPTS/ethercat
    mv $CORE/dnp3.cpp $CORE/dnp3.disabled
    mv $CORE/dnp3_dummy.disabled $CORE/dnp3_dummy.cpp
    # OpenDNP3 is not built for this platform: drop its libraries from every link line;
    # the antminer hardware layer needs libgpiod
    sed -i 's/ -lsnap7 -lasiodnp3 -lasiopal -lopendnp3 -lopenpal/ -lsnap7 -lgpiod/g; s/ -lasiodnp3 -lasiopal -lopendnp3 -lopenpal//g' $SCRIPTS/compile_program.sh
    # let the web UI's "Blank Linux" choice keep our layer instead of the empty one
    sed -i 's#cp ./hardware_layers/blank.cpp ./hardware_layer.cpp#cp ./hardware_layers/antminer.cpp ./hardware_layer.cpp#' $SCRIPTS/change_hardware_layer.sh
    # modbus_master.cpp calls Raspberry-Pi RTS helpers that only exist in OpenPLC's patched
    # libmodbus fork (utils/libmodbus_src); we link the stock libmodbus 3.1.10 -> compile them out
    sed -i -e '/if (rpi_modbus_rts_pin != 0)/i #ifdef OPLC_LIBMODBUS_RPI' \
           -e '/modbus_rpi_pin_export_direction/{n;a #endif' -e '}' $CORE/modbus_master.cpp
    grep -q 'OPLC_LIBMODBUS_RPI' $CORE/modbus_master.cpp || bbfatal "modbus_master.cpp patch did not apply"
    chmod 0755 $SCRIPTS/*.sh
    rm -rf $CORE/*.o $CORE/openplc ${D}${OPENPLC_DIR}/webserver/__pycache__

    install -d ${D}${sysconfdir}/init.d
    install -m 0755 ${WORKDIR}/openplc.init ${D}${sysconfdir}/init.d/openplc
}

# The data partition is 185 MB: drop the parts of the gcc/binutils packages that compiling a PLC
# program never touches (LTO compiler + dump, gold linker, dwp) - about 50 MB.
pkg_postinst_ontarget:${PN}() {
    rm -f /usr/libexec/gcc/*/*/lto1 /usr/bin/*lto-dump /usr/bin/*ld.gold /usr/bin/*-dwp /usr/bin/dwp 2>/dev/null
    rm -rf /var/volatile/cache/opkg/* /var/cache/opkg/* 2>/dev/null
    true
}

# everything (sources, scripts, python, the lib) stays in one package: the target compiles programs
FILES:${PN} = "${OPENPLC_DIR} ${libdir}/libsnap7.so ${sysconfdir}/init.d/openplc"
FILES:${PN}-dev = ""
FILES:${PN}-dbg = ""
INSANE_SKIP:${PN} += "dev-so dev-deps file-rdeps arch staticdev"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"

RDEPENDS:${PN} = " \
    bash \
    matiec \
    python3-core python3-modules \
    python3-flask python3-flask-login python3-flask-jwt-extended python3-flask-sqlalchemy python3-sqlalchemy \
    python3-pyserial python3-pymodbus python3-dotenv python3-six \
    libmodbus libmodbus-dev pkgconfig \
    libgpiod libgpiod-dev \
    gcc gcc-symlinks g++ g++-symlinks cpp cpp-symlinks binutils binutils-symlinks make \
    libc6-dev libstdc++-dev \
    openssl-bin \
    "
# not packagegroup-core-buildessential: it adds autoconf/automake/libtool/gettext and all of
# perl (~60 MB) that compile_program.sh never uses; the data partition is 185 MB
