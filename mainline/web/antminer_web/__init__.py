"""Antminer BB-Black V1.8 I/O module: web UI for provisioning and configuration.

Runs on the provisioning SD card system (antminer-provision-image) and, optionally, on the
NAND system itself (package antminer-web from the feed). Everything it does is a thin layer
over the same command line tools: antminer-flash-nand, antminer-dtb, antminer-data and the
files in /config. No database, no users: the card is in your hand.
"""
__version__ = "0.1"
