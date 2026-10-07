/* Bare-metal I0 -> Q0 echo for the latency measurements (docs/10-latency.md, bare-metal track).
 *
 * Runs directly on the AM3352 after the Bitmain U-Boot ("go 0x82000000"), no OS. Sets up the
 * pads, GPIO2 and the eHRPWM0 stimulus itself (the same pins as the Linux variants: PWM on P9.29,
 * I0 = P8.39 = gpio2_12, Q0 = P8.43 = gpio2_8), then copies I0 to Q0 in a busy loop. Prints a
 * line on the console (UART0, as left by U-Boot) every few million loops. 'r' on the console
 * triggers a warm reset so U-Boot comes back without a power cycle.
 *
 * Build: baremetal/build.sh (WSL, arm-linux-gnueabihf-gcc). Load: antminer.py run bm-echo.bin */
#define REG32(a)  (*(volatile unsigned int *)(a))
#define REG16(a)  (*(volatile unsigned short *)(a))

/* UART0, 16550 compatible, already initialised by U-Boot (115200 8N1) */
#define UART0        0x44E09000u
#define UART_RHR     (UART0 + 0x00)
#define UART_THR     (UART0 + 0x00)
#define UART_LSR     (UART0 + 0x14)

/* Control module: pad configuration and the eHRPWM time-base clock enables */
#define CTRL         0x44E10000u
#define PAD(off)     (CTRL + (off))
#define PWMSS_CTRL   (CTRL + 0x664)
#define CM_CLKSEL_DPLL_MPU 0x44E0042Cu

/* PRCM */
#define CM_PER_GPIO2_CLKCTRL   0x44E000B0u
#define CM_PER_EPWMSS0_CLKCTRL 0x44E000D4u
#define PRM_RSTCTRL            0x44E00F00u

/* GPIO2 */
#define GPIO2        0x481AC000u
#define GPIO_OE          (GPIO2 + 0x134)
#define GPIO_DATAIN      (GPIO2 + 0x138)
#define GPIO_CLEARDATAOUT (GPIO2 + 0x190)
#define GPIO_SETDATAOUT  (GPIO2 + 0x194)
#define I0_BIT       12   /* P8.39 lcd_data6 */
#define Q0_BIT       8    /* P8.43 lcd_data2 */

/* PWMSS0 + eHRPWM0 */
#define PWMSS0       0x48300000u
#define PWMSS_CLKCONFIG (PWMSS0 + 0x08)
#define EPWM0        (PWMSS0 + 0x200)
#define TBCTL        (EPWM0 + 0x00)
#define TBCNT        (EPWM0 + 0x08)
#define TBPRD        (EPWM0 + 0x0A)
#define CMPB         (EPWM0 + 0x14)
#define AQCTLB       (EPWM0 + 0x18)

extern unsigned int __bss_start, __bss_end;

static void putc(char c)
{
    while (!(REG32(UART_LSR) & 0x20)) ;
    REG32(UART_THR) = c;
}
static void puts(const char *s) { while (*s) { if (*s == '\n') putc('\r'); putc(*s++); } }
static void putu(unsigned int v)
{
    char b[12]; int i = 0;
    if (!v) { putc('0'); return; }
    while (v) { b[i++] = '0' + v % 10; v /= 10; }
    while (i) putc(b[--i]);
}

static void module_enable(unsigned int clkctrl)
{
    REG32(clkctrl) = 2;                               /* MODULEMODE = enable */
    while (REG32(clkctrl) & (3u << 16)) ;             /* IDLEST = functional */
}

static void setup(void)
{
    for (unsigned int *p = &__bss_start; p < &__bss_end; p++) *p = 0;

    /* pads: Q0 output mode 7 pull-down, I0 input mode 7 pull-up, P9.29 ehrpwm0B */
    REG32(PAD(0x8A8)) = 0x07;
    REG32(PAD(0x8B8)) = 0x37;
    REG32(PAD(0x994)) = 0x01;

    /* GPIO2: Q0 output low, I0 input */
    module_enable(CM_PER_GPIO2_CLKCTRL);
    REG32(GPIO_CLEARDATAOUT) = 1u << Q0_BIT;
    REG32(GPIO_OE) = (REG32(GPIO_OE) & ~(1u << Q0_BIT)) | (1u << I0_BIT);

    /* stimulus: eHRPWM0 channel B, 187.37 ms period, 50 % (TBCLK = 100 MHz / 14 / 128) */
    module_enable(CM_PER_EPWMSS0_CLKCTRL);
    REG32(PWMSS_CTRL) |= 1;                           /* ehrpwm0 TBCLK enable */
    REG32(PWMSS_CLKCONFIG) = 0x111;                   /* eCAP/eQEP/ePWM clocks on */
    REG16(TBCTL) = 0x9F80;                            /* free run, CLKDIV /128, HSPCLKDIV /14, count up */
    REG16(TBPRD) = 10455;
    REG16(CMPB)  = 5228;
    REG16(AQCTLB) = 0x0102;                           /* set on zero, clear on CMPB (up) */
    REG16(TBCNT) = 0;
}

int main(void)
{
    setup();
    unsigned int clksel = REG32(CM_CLKSEL_DPLL_MPU);
    puts("\nbm-echo: bare-metal I0 -> Q0 echo, AM3352, no OS\n");
    puts("MPU DPLL M=");  putu((clksel >> 8) & 0x7FF); puts(" N="); putu(clksel & 0x7F);
    puts("  (f = 24 MHz * M / (N+1) / M2)\n");
    puts("stimulus on P9.29, I0 = P8.39, Q0 = P8.43; 'r' resets\n");

    unsigned int last = (REG32(GPIO_DATAIN) >> I0_BIT) & 1, edges = 0, loops = 0;
    for (;;) {
        unsigned int v = (REG32(GPIO_DATAIN) >> I0_BIT) & 1;
        if (v != last) {
            if (v) REG32(GPIO_SETDATAOUT) = 1u << Q0_BIT; else REG32(GPIO_CLEARDATAOUT) = 1u << Q0_BIT;
            last = v; edges++;
        }
        if (++loops == (1u << 24)) {                  /* status line now and then, off the hot path */
            loops = 0;
            puts("edges "); putu(edges); puts("\n");
            if ((REG32(UART_LSR) & 1) && (REG32(UART_RHR) & 0xFF) == 'r') {
                puts("warm reset\n");
                REG32(PRM_RSTCTRL) = 1;
            }
        }
        if (REG32(UART_LSR) & 1) {                    /* console input: 'r' = warm reset */
            if ((REG32(UART_RHR) & 0xFF) == 'r') { puts("warm reset\n"); REG32(PRM_RSTCTRL) = 1; }
        }
    }
}
