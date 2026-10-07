FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
# hardware watchdog feeder + a few conveniences poky's defconfig leaves out
SRC_URI += "file://antminer.cfg"
