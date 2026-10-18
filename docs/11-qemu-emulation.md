# 11. Can the board be emulated in QEMU? (feasibility study)

Date: 2026-10-18. Question: can an exact virtual copy of the Antminer BB-Black V1.8 (AM3352) be
built with QEMU, and how exact would it be?

**Short answer: no exact copy is possible.** QEMU has no AM335x model and never had one. The
software can be copied exactly (variant 1 and 2 below), the hardware cannot. Writing an AM335x
machine model (variant 3) is feasible but is 8-10 thousand lines of C and several person-months,
and even then it does not validate the one thing this project depends on most: the pinmux.

## The three levels of "copy"

| variant | what is exact | what is missing | effort |
|---|---|---|---|
| 1. `qemu-arm` user mode + our rootfs in a chroot | binaries, packages, scripts | kernel, boot, all hardware | hours |
| 2. `qemu-system-arm -M virt` with the same initramfs and a kernel 6.12 built with a `virt` config | the whole userspace: busybox init, dropbear, web UI, OpenPLC, Modbus TCP, overlay logic | MLO/U-Boot 2013.04, NAND mtd0-10, pinmux, GPIO, ADC, UART1-5, I2C, watchdog | days |
| 3. own AM335x machine model in QEMU | address map, interrupts, boot from SPL onwards | ROM bootloader, timing, electrical behaviour | months |

Variant 2 is what Yocto itself does for `beaglebone-yocto` (`runqemu` on `virt`). Missing GPIO
lines can be faked with the kernel module `gpio-sim`, so `gpioinfo` and OpenPLC see the same line
names. Our current kernel config has `ARCH_VIRT`, `GPIO_SIM` and `VIRTIO` disabled; a second
config (or a merged one) would be needed. Variant 2 covers almost everything worth testing
automatically: initramfs assembly, service start-up, the web UI, OpenPLC programs, Modbus
registers. Everything touching pinmux, DTB overlays, NAND, boot or timing stays on real hardware.

The rest of this document is the detailed study of variant 3.

## Prior art: none

- **Upstream QEMU** never had AM335x. The old `-M beagle` was OMAP3 in the dead qemu-linaro fork.
- **QEMU 9.2 (October 2024)** removed all OMAP2 machines (n800, n810) and PXA2xx machines together
  with their SoC code, "very old and unmaintained". Only OMAP1 (`sx1`, `omap1.c`) remains, status
  "Odd Fixes" (maintainer Peter Maydell). OneNAND and the generic `nand.c` chip model were removed
  with them; `hcd-musb.c` and `tusb6010.c` are gone too.
- **qemu-devel, GitHub, GitLab**: no patches, no fork, no project adding an AM335x or BeagleBone
  machine. Hobby projects that claim "BeagleBone on QEMU" all boot a different machine (`virt` or
  the OMAP3 `beagle`) with a different DTB.
- **Renode**: no AM335x/AM33xx/Sitara/OMAP platform; its Cortex-A platforms are A9, A53, A78.
- **Boot ROM**: `sjgallagher2/am335xbootrom` (MIT) is a partial Ghidra reverse engineering of the
  AM3358 ROM, mostly the MMC path, no executable model. Not needed anyway: a QEMU machine would
  load MLO directly into SRAM at 0x402F0400 with a fake boot-parameters structure.

## What our board actually uses (from the DTB and dmesg)

Fixed part (`firmware/dts/am335x-antminer-base.dtsi` + `am33xx.dtsi`), all behind `ti,sysc`
target modules and the `ti,am3-prcm` clock controller:

| block | compatible / driver | used for |
|---|---|---|
| CPU | arm,cortex-a8, 600 MHz, no PRU, no SGX | |
| INTC | ti,am33xx-intc (irq-omap-intc) | 128 interrupts, 4 banks |
| timers | ti,am335x-timer-1ms (timer1, clockevent), ti,am335x-timer (timer2, clocksource) | |
| PRCM | ti,am3-prcm: ti,clkctrl, ti,am3-dpll-*, prm resets | every module's clock and reset |
| control module | ti,am3-scm: pinctrl-single, efuse MAC, device ID, gmii-sel, usb-ctrl | |
| UART0..5 | ti,am3352-uart (8250_omap) | console on UART0, Modbus RTU on others |
| GPIO0..3 | ti,omap4-gpio | all I/O lines, LEDs |
| I2C0, I2C2 | ti,omap4-i2c | TPS65217 PMIC at 0x24; LM75 etc. on I2C2 |
| MMC0 | ti,am335-sdhci (sdhci-omap) | microSD, "using External DMA" (EDMA) |
| GPMC + ELM | ti,am3352-gpmc, ti,am3352-elm (omap2-nand, BCH8 HW, prefetch-dma) | 256 MB Micron MT29F2G08ABAEAWP |
| EDMA | ti,edma3-tpcc + 3 tptc | NAND, MMC, UART0-2 |
| CPSW | ti,am335x-cpsw-switch + ti,cpsw-mdio, SMSC LAN8710 PHY | Ethernet |
| TSCADC | ti,am3359-tscadc / adc | IIO ADC |
| watchdog | ti,omap3-wdt | 60 s, always on |
| RTC | ti,am3352-rtc | time without battery |
| crypto, misc | omap4-sham, omap4-aes, omap4-rng, mailbox, hwspinlock | probed, not needed |
| disabled | musb, pruss, sgx, pwmss, mcasp, lcdc, d_can, spi, emif, wkup_m3 | |

Boot path on the board: ROM → SPL (MLO, U-Boot 2013.04) from NAND → U-Boot → uImage + initramfs +
DTB from mtd7/8/6 → kernel 6.12. SPL and U-Boot talk to the PMIC over I2C0, probe MMC (time out
without a card), initialise musb and cpsw, and read NAND with BCH8 + ELM.

## What exists in QEMU and what can be revived

QEMU still has the Cortex-A8 CPU (used by `cubieboard`, Allwinner A10). The A10 SoC glue
(`hw/arm/allwinner-a10.c`) is ~300 lines and a good template for the machine file. Everything
else:

| QEMU model | state today | use for AM335x |
|---|---|---|
| `hw/intc/omap_intc.c` | OMAP1 only (406 lines). The OMAP2 variant exists in tag v9.1.0 (673 lines, 3 banks hard-coded, no THRESHOLD register, off-by-one in the ILR bounds check) | revive from v9.1.0, extend to 4 banks / 128 IRQs. Linux uses the same programming model for am33xx as for OMAP2/3 |
| `hw/timer/omap_gptimer.c` | removed; v9.1.0 has 510 lines, OMAP2 register layout, depends on `omap_clk` | layout matches only timer1 (the 1 ms timer) and lacks the 1 ms registers (TPIR/TNIR/TOCR/TOWR). The other AM335x dmtimers use a different map (IRQSTATUS 0x28, TCLR 0x38 ... TCAR2 0x58) |
| `hw/misc/omap_gpmc.c` | removed; v9.1.0 has ~800 lines: per-CS CONFIG1-7, NAND cmd/addr/data windows, prefetch FIFO, Hamming ECC only | revive; add BCH8 result registers (a BCH encoder with TI's polynomial; the kernel XORs the software result with a 13-byte constant to match the hardware) |
| `hw/block/nand.c` | removed; v9.1.0 has ~830 lines, knows chip ID 0xda (256 MB, 2 KB page, x8), no ONFI parameter page | revive. READID returns "QEMU" as the 3rd-6th ID bytes; the kernel's extended-ID decode would read a 64 KB erase size instead of 128 KB. Return Micron's real `2c da 90 95 06` instead (a few lines) |
| `hw/char/omap_uart.c` | 64 lines: a 16550 (`serial-mm`, regshift 2) with no OMAP registers at all | new layer needed: MVER, MDR1, SCR, WER, SYSC/SYSS, TX_LVL, RX_LVL |
| `hw/gpio/omap_gpio.c`, `hw/i2c/omap_i2c.c` | OMAP1/OMAP2 register layouts | useless; AM335x uses the OMAP4 layouts |
| `hw/sd/omap_mmc.c` | OMAP1 MMC | useless; AM335x MMC is an SDHCI core at +0x200 with a TI block at +0x100 |
| `hw/sd/sdhci.c` | maintained | the core under a TI wrapper |
| CPSW, CPDMA, davinci_mdio, EDMA, ELM, TSCADC, PRCM, control module, omap wdt, am3352 RTC, musb | never existed in any version | new |

## What the kernel 6.12 drivers demand from a model

Checked in the drivers our DTB enables, to separate "write and read back" registers from
behaviour that must be modelled:

- **PRCM (drivers/clk/ti/clkctrl.c, dpll3xxx.c).** The clkctrl driver writes MODULEMODE (bits
  1:0) and polls IDLEST (bits 17:16) for 0 (functional) or 2 (interface idle) within 2000 us;
  on timeout: `pr_err("%s: failed to enable")`, -EBUSY, the module is not probed. The DPLL driver
  polls the lock bit in the IDLEST register up to 1 s per DPLL (`clock: %s failed transition to
  'locked'`). Five DPLLs. Reset lines (RM_*_RSTCTRL/RSTST) are a reset controller. This is a
  functional model of ~500 lines, not RAM.
- **ti-sysc (drivers/bus/ti-sysc.c).** Reads REVISION, writes SYSCONFIG, soft-resets and polls
  SYSSTATUS/RESETDONE with a 10000-iteration timeout. A reset timeout during init fails the probe
  (`Reset failed with %d`). Unknown revision values are accepted silently.
- **Control module (mach-omap2/id.c).** Reads TAP IDCODE at 0x0204, hawkeye 0xb944 = AM335x,
  rev 0/1/2 = ES1.0/2.0/2.1; an unknown idcode is reported as "OMAP3630ES1.2" with a warning. Also
  efuse MAC (`mac_id0_lo/hi`), DEV_FEATURE, control_status (SYSBOOT). The pinmux region is plain
  RAM for pinctrl-single.
- **INTC (irq-omap-intc.c).** am33xx = 128 IRQs, 4 banks; soft reset via SYSCONFIG bit 1 and
  poll SYSSTATUS bit 0; SIR at 0x40 masked with 0x7f, spurious mask `0x1ffffff << 7`; ack by
  writing 1 to CONTROL (0x48); MIR_SET/MIR_CLEAR at 0x8c/0x88 + 0x20*bank; ILR at 0x100. Same as
  OMAP2/3.
- **UART (8250_omap.c).** Reads MVER for the revision (scheme bit 30; known 0x0406, 0x0502,
  0x0603; unknown → "Unknown revision, defaulting to highest", no errata, boots fine). Writes
  MDR1, SCR, WER. Soft reset through SYSC/SYSS only in runtime suspend (`UART_ERRATA_CLOCK_DISABLE`
  for ti,am3352-uart). DMA is used only when `dma-names` has 2 entries, and never on the console
  port. UART0-2 and MMC0 have EDMA channels in `am33xx-l4.dtsi`; UART3-5 do not.
- **MMC (sdhci-omap.c).** `ti,am335-sdhci`: omap_offset 0x100, SDHCI at 0x200, flag
  SDHCI_OMAP_SPECIAL_RESET (poll the reset bits to set, then clear). TI registers: SYSCONFIG 0x110,
  CON 0x12c, DLL 0x134, HCTL 0x228, SYSCTL 0x22c, STAT 0x230, IE/ISE 0x234/0x238, AC12 0x23c,
  CAPA 0x240. `conf_bus_power` polls HCTL_SDBP, `init_74_clocks` sets CON_INIT and polls STAT for
  INT_CC_EN (1 ms, WARN_ON and the host IRQ stays disabled on timeout), `card_busy` reads
  PSTATE_DLEV_DAT0. A bare QEMU SDHCI model at +0x200 does not boot: the TI block must answer.
  Without `dmas` the driver uses the SDHCI's own ADMA, which QEMU's `sdhci.c` supports.
- **NAND (mtd/nand/raw/omap2.c).** BCH8 HW: ECC_CONFIG/CONTROL/SIZE_CONFIG, BCH_RESULT0..3 per
  sector read into 13 ECC bytes (14th cleared "for ROM compatibility"), prefetch engine in DMA
  mode via `dma_request_chan("rxtx")` with CPU-copy fallback. Correction: all-zero or erased
  sectors are skipped, few bit flips are fixed in software, the rest go to the ELM. In an emulator
  with an error-free image the ELM is only configured (`elm_config`) and reset, never asked to
  decode; a near-stub suffices. Without `ti,elm-id` the kernel switches to
  `OMAP_ECC_BCH8_CODE_HW_DETECTION_SW` (software correction). The BCH8 encoder in the GPMC model
  must be bit-exact, otherwise every sector is "uncorrectable bit-flips found".
- **CPSW (cpsw_new.c, cpsw_ale.c, davinci_cpdma.c, davinci_mdio.c).** Soft reset bits that must
  self-clear (cpsw, each MAC SL, MDIO), ALE table through TBLCTL/TBLW/TBLR, CPDMA descriptor rings
  in the controller's internal RAM (`CPSW2_BD_OFFSET`), host/slave port registers, CPTS, MDIO
  with alive/link registers and a clause-22 PHY (LAN8710 ID 0x0007c0f1). No comparable model
  exists. Reference sizes: `allwinner_emac.c` 539 lines (FIFO MAC, fake RTL8201 PHY, `qemu_new_nic`
  wiring), `cadence_gem.c` ~1350 lines (descriptor DMA, PHY over MDIO, per-queue IRQs).

## The SPL / U-Boot path

Booting the Bitmain SPL and U-Boot 2013.04 from the NAND image is a separate problem from the
kernel. From the boot log (`device-dump/nandboot-14-after-card-pull.log`) and U-Boot's am33xx code,
the SPL expects: watchdog disable sequence, DPLL lock bits in CM_WKUP, the VTP_CTRL READY bit in
the control module, EMIF/DDR PHY registers, an I2C slave answering as TPS65217 at 0x24, musb
configuration registers (it prints `ConfigData=0xde`, `MHDRC RTL version 2.0`), MMC probing that
is allowed to time out, cpsw soft reset bits, and GPMC NAND reads with BCH8 where it compares the
calculated ECC with the stored ECC and calls the ELM only when they differ. Each of these is found
by trial and error on the serial log. Estimate: 1-2 months on top of the kernel-only model.
The ROM itself is not emulated: MLO is loaded into SRAM by the machine model.

## Effort estimate

Lines of new or adapted C, kernel-boot first:

| part | lines | note |
|---|---|---|
| machine + SoC glue, RAM, SRAM, boot | 400 | after `allwinner-a10.c` |
| INTC | 300 | from v9.1.0 |
| dmtimer, two register layouts | 600 | timer1 clockevent, timer2 clocksource |
| PRCM/CM/PRM functional model | 500 | new |
| control module | 250 | new |
| UART OMAP layer x6 | 250 | over `serial-mm` |
| GPIO OMAP4 x4 | 350 | new |
| I2C OMAP4 + TPS65217 slave | 600 | new; U-Boot writes the PMIC |
| sdhci-omap wrapper | 300 | over `sdhci.c` |
| GPMC + NAND chip + BCH8 + ELM stub | 1200 | from v9.1.0 plus BCH |
| CPSW + CPDMA + ALE + MDIO + PHY | 2000 | new |
| watchdog, RTC, TSCADC | 850 | new; the watchdog must really reset the VM |
| stubs: mailbox, hwspinlock, sham, aes, rng, musb, pwmss, mcasp, lcdc, emif, wkup_m3 | 100 | `create_unimplemented_device` or disabled in the virtual DTB |
| EDMA | 0 or 1000 | 0 if the virtual DTB drops `dmas`/`dma-names` (NAND polled, MMC ADMA, UART PIO) |

Total 7700-8700 lines without EDMA. For someone who knows QEMU: 4-6 months to a model that boots
our kernel with network, NAND and GPIO. SPL/U-Boot adds 1-2 months. Injecting GPIO/ADC stimuli
from outside (QMP commands or a chardev protocol) adds 2-4 weeks; QEMU has no generic way to drive
a GPIO input. The model lives out of tree and has to be carried across QEMU releases; upstreaming
needs functional tests and a maintainer while the TI/OMAP code there is "Odd Fixes".

A sensible staging if it is ever done: first an "AM335x-lite" machine with INTC, dmtimer, UART,
PRCM, control module, GPIO and I2C (~3000 lines, 4-6 weeks) plus virtio-mmio for disk and network.
That already boots the real kernel and a lightly modified DTB with the real drivers for interrupts,
timers, console and GPIO. Then GPMC/NAND, then CPSW, last SPL/U-Boot.

## How exact the result would be

Exact, in the sense that the drivers cannot tell the difference: address map, interrupt numbers,
the register semantics our drivers use, the NAND image with the real partitions and content, the
boot sequence, the whole userspace.

Approximate: time. TCG is not cycle accurate; `icount` gives determinism, not realism. Clock
frequencies are whatever was written into the PRCM, the OPP table and cpufreq are meaningless.
The 49 us edge wake-up and 1.3 ms OpenPLC cycle from [10-latency](10-latency.md) cannot be
reproduced.

Absent: pinmux. The pinctrl-single region is RAM; the model does not know which pad goes to which
module, so a wrong mux in a profile does not show up as an error. Also absent: electrical
behaviour, SYSBOOT resistors, PMIC behaviour, temperature (bandgap), NAND bit flips and wear
(could be injected artificially), PHY link physics, the RTC without a battery.

This is the decisive point. The main risk in this project is the pinmux profiles, and that is
exactly what the model cannot validate. It would validate the kernel, the DTB structure, the NAND
image, boot and services. Of those, only the kernel and the NAND image are not already covered by
variant 2 on `virt`.

## Sources

- QEMU `docs/about/removed-features.rst` (Arm machines removed in 9.2), `hw/arm/meson.build`,
  `hw/arm/Kconfig`, `MAINTAINERS`, `hw/*/meson.build` (master, 2026-10-18)
- QEMU tag v9.1.0: `hw/intc/omap_intc.c`, `hw/timer/omap_gptimer.c`, `hw/misc/omap_gpmc.c`,
  `hw/block/nand.c`
- QEMU master: `hw/arm/allwinner-a10.c`, `hw/net/allwinner_emac.c`, `hw/net/cadence_gem.c`,
  `hw/char/omap_uart.c`, `hw/gpio/omap_gpio.c`, `hw/i2c/omap_i2c.c`
- QEMU commits: "hw/arm: Remove 'n800' and 'n810' machines", "hw/block: Remove OneNAND device",
  "hw/block: Drop unused nand.c" (Peter Maydell, 2024)
- Linux v6.12: `drivers/clk/ti/clkctrl.c`, `drivers/clk/ti/dpll3xxx.c`, `drivers/bus/ti-sysc.c`,
  `drivers/irqchip/irq-omap-intc.c`, `drivers/tty/serial/8250/8250_omap.c`,
  `drivers/mmc/host/sdhci-omap.c`, `drivers/mtd/nand/raw/omap2.c`,
  `drivers/net/ethernet/ti/cpsw_new.c`, `arch/arm/mach-omap2/id.c`,
  `arch/arm/boot/dts/ti/omap/am33xx-l4.dtsi`
- Renode `platforms/cpus` (GitHub, master)
- https://github.com/sjgallagher2/am335xbootrom
- https://github.com/electricalgorithm/kabanos/pull/3, https://github.com/marwan475/Qemu-Beagle
- TI E2E: "linux processor sdk am335x qemu emulation"
  (https://e2e.ti.com/support/processors-group/processors/f/processors-forum/591794)
- OE-core 2019: "yocto-bsp: runqemu runs beaglebone-yocto" (on `virt`)
- U-Boot `include/configs/bur_am335x_common.h`, "ARM:AM33XX: Add SPL support for AM335X EVM"
  (2012)
- Local: `device-dump/dmesg.txt`, `device-dump/sysinfo.txt`,
  `device-dump/nandboot-14-after-card-pull.log`, `firmware/out/am335x-antminer-base.pp.dtsi`,
  `firmware/out/config-6.12.112-dirty`
