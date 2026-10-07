SUMMARY = "Per-board device tree generator for the Antminer I/O module, runnable on the board"
DESCRIPTION = "gen-dts.py, the pad database, the board profiles and a cpp-preprocessed copy of \
the fixed device tree (am335x-antminer-base.pp.dtsi). With dtc that is everything needed to turn \
a YAML profile into a DTB on the target: antminer-dtb build boards/x.yaml -> flash to mtd6."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

FILESEXTRAPATHS:prepend := "${ANTMINER_FIRMWARE_DIR}/pinmux:${ANTMINER_FIRMWARE_DIR}/dts:${THISDIR}/files:"
SRC_URI = "file://gen-dts.py \
           file://am335x-bbb-pins.json \
           file://boards \
           file://am335x-antminer-base.dtsi \
           file://antminer-dtb \
           "

S = "${WORKDIR}"
PACKAGE_ARCH = "${MACHINE_ARCH}"
COMPATIBLE_MACHINE = "antminer-bbb"
inherit deploy

# the preprocessed base needs the kernel's dts/ and include/dt-bindings/ trees; the shipped
# profiles are also compiled here (dtc-native) and deployed, so the SD card carries a DTB per profile
DEPENDS = "virtual/kernel dtc-native python3-pyyaml-native python3-native"
do_compile[depends] += "virtual/kernel:do_shared_workdir"

PINMUX_DIR = "${datadir}/antminer/pinmux"

do_compile() {
    KSRC="${STAGING_KERNEL_DIR}"
    DTSDIR="$KSRC/arch/arm/boot/dts/ti/omap"
    [ -f "$DTSDIR/am33xx.dtsi" ] || bbfatal "kernel dts tree not found in $KSRC"
    printf '#include "am335x-antminer-base.dtsi"\n' | \
    ${CPP} -nostdinc -undef -D__DTS__ -x assembler-with-cpp -P \
        -I "${WORKDIR}" -I "$DTSDIR" -I "$KSRC/arch/arm/boot/dts" -I "$KSRC/include" - \
        | sed '/^[[:space:]]*$/d' > base.tmp
    # inline dtc-style /include/ lines (bone-common: ../../tps65217.dtsi) and drop /dts-v1/
    python3 - base.tmp am335x-antminer-base.pp.dtsi "$DTSDIR" <<'EOF'
import os, re, sys
src, dst, dtsdir = sys.argv[1:4]
inc = re.compile(r'^\s*/include/\s*"([^"]+)"\s*$')
def expand(text, base):
    out = []
    for line in text.splitlines():
        m = inc.match(line)
        if m:
            path = os.path.normpath(os.path.join(base, m.group(1)))
            with open(path) as fh:
                out.append(f"/* inlined {m.group(1)} */")
                out.append(expand(fh.read(), os.path.dirname(path)))
        else:
            out.append(line)
    return "\n".join(out)
with open(src) as fh:
    body = expand(fh.read(), dtsdir)
body = re.sub(r"^\s*/dts-v1/;\s*$", "", body, flags=re.M)
with open(dst, "w") as fh:
    fh.write(body.strip() + "\n")
EOF
    grep -qE '^\s*#(include|define)|AM33XX_IOPAD|^\s*/include/' am335x-antminer-base.pp.dtsi && bbfatal "preprocessor leftovers" || true

    # every shipped profile -> DTB, exactly the way the board does it (gen-dts --flat + dtc)
    mkdir -p dtbs
    for y in boards/*.yaml; do
        n=$(basename "$y" .yaml)
        python3 gen-dts.py "$y" --flat am335x-antminer-base.pp.dtsi -o "dtbs/am335x-antminer-$n.dts" || bbfatal "profile $n does not generate"
        dtc -I dts -O dtb -i "${WORKDIR}" -o "dtbs/am335x-antminer-$n.dtb" "dtbs/am335x-antminer-$n.dts" 2> dtbs/$n.log || { cat dtbs/$n.log; bbfatal "profile $n does not compile"; }
    done
}

do_deploy() {
    # profile-<name>.dtb: a distinct prefix so the SD image can pick them up with one wildcard
    # without catching the kernel's own am335x-antminer-*.dtb deploy copies
    install -d ${DEPLOYDIR}
    for f in ${B}/dtbs/am335x-antminer-*.dtb; do
        n=$(basename "$f" .dtb); n=${n#am335x-antminer-}
        install -m 0644 "$f" ${DEPLOYDIR}/profile-$n.dtb
    done
}
addtask deploy after do_compile before do_build

do_install() {
    install -d ${D}${PINMUX_DIR}/boards ${D}${sbindir}
    install -m 0755 ${WORKDIR}/gen-dts.py ${D}${PINMUX_DIR}/gen-dts.py
    install -m 0644 ${WORKDIR}/am335x-bbb-pins.json ${D}${PINMUX_DIR}/
    install -m 0644 ${WORKDIR}/am335x-antminer-base.pp.dtsi ${D}${PINMUX_DIR}/
    install -m 0644 ${WORKDIR}/boards/*.yaml ${D}${PINMUX_DIR}/boards/
    install -m 0755 ${WORKDIR}/antminer-dtb ${D}${sbindir}/antminer-dtb
}

FILES:${PN} = "${PINMUX_DIR} ${sbindir}/antminer-dtb"
RDEPENDS:${PN} = "python3-core python3-json python3-pyyaml dtc mtd-utils busybox"
