/* Entry for programs started by U-Boot's "go": we arrive in SVC mode with U-Boot's MMU/cache
 * state (DRAM cacheable, peripherals strongly ordered). Own stack near the top of the 256 MB,
 * far from the load address 0x82000000 and from U-Boot's own area at the very end. */
    .syntax unified
    .arm
    .section .text.start, "ax"
    .global _start
_start:
    ldr     sp, =0x8E000000
    bl      main
1:  b       1b

    .section .note.GNU-stack, "", %progbits
