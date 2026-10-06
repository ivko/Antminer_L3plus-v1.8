//-----------------------------------------------------------------------------
// OpenPLC hardware layer for the Antminer BB-Black V1.8 I/O module (AM3352).
//
// Digital I/O goes through libgpiod v2 using the line names the board's device
// tree gives the pads (pinmux/boards/*.yaml -> gpio-line-names):
//   lines "I0".."I127"  -> %IX0.0 .. %IX15.7   (inputs)
//   lines "Q0".."Q127"  -> %QX0.0 .. %QX15.7   (outputs, driven every cycle)
// Analog inputs are the eight AM335x ADC channels (1.8 V, 12 bit) via IIO:
//   /sys/bus/iio/devices/iio:device0/in_voltageN_raw -> %IW0 .. %IW7
// Nothing is hard-coded about the pins: change the YAML profile, reflash the
// DTB, and the same binary follows the new names.
//
// Build: compiled together with the generated program by scripts/compile_program.sh
// (needs libgpiod-dev; the link line carries -lgpiod).
//-----------------------------------------------------------------------------
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <pthread.h>
#include <gpiod.h>
#include "ladder.h"

#define MAX_DIGITAL 128
#define MAX_ADC 8
#define IIO_DIR "/sys/bus/iio/devices/iio:device0"

struct line {
    struct gpiod_line_request *req;
    unsigned int offset;
    bool used;
};

static struct line inputs[MAX_DIGITAL];
static struct line outputs[MAX_DIGITAL];
static int adc_fd[MAX_ADC];
static int n_in = 0, n_out = 0, n_adc = 0;

static struct gpiod_line_request *request_line(struct gpiod_chip *chip, unsigned int offset,
                                               bool output, const char *name)
{
    struct gpiod_line_settings *settings = gpiod_line_settings_new();
    struct gpiod_line_config *lcfg = gpiod_line_config_new();
    struct gpiod_request_config *rcfg = gpiod_request_config_new();
    struct gpiod_line_request *req = NULL;
    if (!settings || !lcfg || !rcfg) goto out;
    gpiod_line_settings_set_direction(settings, output ? GPIOD_LINE_DIRECTION_OUTPUT : GPIOD_LINE_DIRECTION_INPUT);
    if (output) gpiod_line_settings_set_output_value(settings, GPIOD_LINE_VALUE_INACTIVE);
    if (gpiod_line_config_add_line_settings(lcfg, &offset, 1, settings) < 0) goto out;
    gpiod_request_config_set_consumer(rcfg, "openplc");
    req = gpiod_chip_request_lines(chip, rcfg, lcfg);
    if (!req) perror(name);
out:
    if (rcfg) gpiod_request_config_free(rcfg);
    if (lcfg) gpiod_line_config_free(lcfg);
    if (settings) gpiod_line_settings_free(settings);
    return req;
}

// scan every gpiochip for lines named I<n> / Q<n>
static void scan_gpio(void)
{
    char path[32], name[16];
    for (int c = 0; c < 8; c++) {
        snprintf(path, sizeof(path), "/dev/gpiochip%d", c);
        if (access(path, F_OK) != 0) continue;
        struct gpiod_chip *chip = gpiod_chip_open(path);
        if (!chip) continue;
        for (int n = 0; n < MAX_DIGITAL; n++) {
            snprintf(name, sizeof(name), "I%d", n);
            int off = gpiod_chip_get_line_offset_from_name(chip, name);
            if (off >= 0 && !inputs[n].used) {
                struct gpiod_line_request *r = request_line(chip, off, false, name);
                if (r) { inputs[n].req = r; inputs[n].offset = off; inputs[n].used = true; n_in++; }
            }
            snprintf(name, sizeof(name), "Q%d", n);
            off = gpiod_chip_get_line_offset_from_name(chip, name);
            if (off >= 0 && !outputs[n].used) {
                struct gpiod_line_request *r = request_line(chip, off, true, name);
                if (r) { outputs[n].req = r; outputs[n].offset = off; outputs[n].used = true; n_out++; }
            }
        }
        // requests keep the chip alive; the chip handle itself can go
        gpiod_chip_close(chip);
    }
}

static void open_adc(void)
{
    char path[96];
    for (int ch = 0; ch < MAX_ADC; ch++) {
        snprintf(path, sizeof(path), IIO_DIR "/in_voltage%d_raw", ch);
        adc_fd[ch] = open(path, O_RDONLY);
        if (adc_fd[ch] >= 0) n_adc++;
    }
}

static int read_adc(int ch)
{
    char buf[16];
    if (adc_fd[ch] < 0) return 0;
    if (lseek(adc_fd[ch], 0, SEEK_SET) < 0) return 0;
    ssize_t n = read(adc_fd[ch], buf, sizeof(buf) - 1);
    if (n <= 0) return 0;
    buf[n] = 0;
    return atoi(buf);
}

void initializeHardware()
{
    memset(inputs, 0, sizeof(inputs));
    memset(outputs, 0, sizeof(outputs));
    for (int i = 0; i < MAX_ADC; i++) adc_fd[i] = -1;
    scan_gpio();
    open_adc();
    printf("antminer hardware layer: %d inputs (I*), %d outputs (Q*), %d ADC channels\n", n_in, n_out, n_adc);
}

void finalizeHardware()
{
    for (int n = 0; n < MAX_DIGITAL; n++) {
        if (inputs[n].used) { gpiod_line_request_release(inputs[n].req); inputs[n].used = false; }
        if (outputs[n].used) {
            // leave outputs low (the DTS pull resistors define the same idle level)
            gpiod_line_request_set_value(outputs[n].req, outputs[n].offset, GPIOD_LINE_VALUE_INACTIVE);
            gpiod_line_request_release(outputs[n].req); outputs[n].used = false;
        }
    }
    for (int i = 0; i < MAX_ADC; i++) if (adc_fd[i] >= 0) { close(adc_fd[i]); adc_fd[i] = -1; }
}

void updateBuffersIn()
{
    pthread_mutex_lock(&bufferLock);
    for (int n = 0; n < MAX_DIGITAL; n++) {
        if (!inputs[n].used || bool_input[n / 8][n % 8] == NULL) continue;
        enum gpiod_line_value v = gpiod_line_request_get_value(inputs[n].req, inputs[n].offset);
        *bool_input[n / 8][n % 8] = (v == GPIOD_LINE_VALUE_ACTIVE);
    }
    for (int ch = 0; ch < MAX_ADC; ch++) {
        if (adc_fd[ch] >= 0 && int_input[ch] != NULL) *int_input[ch] = (IEC_UINT)read_adc(ch);
    }
    pthread_mutex_unlock(&bufferLock);
}

void updateBuffersOut()
{
    pthread_mutex_lock(&bufferLock);
    for (int n = 0; n < MAX_DIGITAL; n++) {
        if (!outputs[n].used || bool_output[n / 8][n % 8] == NULL) continue;
        gpiod_line_request_set_value(outputs[n].req, outputs[n].offset,
                                     *bool_output[n / 8][n % 8] ? GPIOD_LINE_VALUE_ACTIVE : GPIOD_LINE_VALUE_INACTIVE);
    }
    pthread_mutex_unlock(&bufferLock);
}
