/* Flat binary loaded by U-Boot at 0x82000000 and started with "go 0x82000000":
 * the first bytes must be _start, so every ELF housekeeping section is discarded. */
ENTRY(_start)
SECTIONS
{
    . = 0x82000000;
    .text   : { KEEP(*(.text.start)) *(.text*) }
    .rodata : { *(.rodata*) }
    .data   : { *(.data*) }
    . = ALIGN(4);
    __bss_start = .;
    .bss    : { *(.bss*) *(COMMON) }
    . = ALIGN(4);
    __bss_end = .;
    /DISCARD/ : { *(.note*) *(.interp) *(.dynsym) *(.dynstr) *(.hash) *(.gnu.hash) *(.dynamic)
                  *(.ARM.exidx*) *(.ARM.extab*) *(.ARM.attributes) *(.comment) *(.eh_frame*) }
}
