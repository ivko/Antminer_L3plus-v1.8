/* Minimal input-to-output echo for the latency measurements (docs/10-latency.md): copies GPIO
 * line "I0" to line "Q0" as fast as Linux allows, without a PLC runtime.
 *
 *   gcc -O2 -o latency-echo latency-echo.c -lgpiod        (on the board: gcc + libgpiod-dev from the feed)
 *   ./latency-echo              # poll as fast as possible, SCHED_FIFO 80, memory locked
 *   ./latency-echo 1000         # poll every 1000 us (clock_nanosleep), like a 1 ms PLC cycle
 *   ./latency-echo -e           # sleep in the kernel until an edge on I0 (gpiod edge events)
 *
 * Stop OpenPLC first (/etc/init.d/openplc stop): it holds the same lines.  libgpiod v2 API. */
#include <errno.h>
#include <gpiod.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stop;
static void on_sig(int s) { (void)s; stop = 1; }

static struct gpiod_line_request *request(const char *name, int output, int edges, struct gpiod_chip **chip_out)
{
    char path[32];
    for (int c = 0; c < 8; c++) {
        snprintf(path, sizeof path, "/dev/gpiochip%d", c);
        struct gpiod_chip *chip = gpiod_chip_open(path);
        if (!chip) continue;
        int off = gpiod_chip_get_line_offset_from_name(chip, name);
        if (off < 0) { gpiod_chip_close(chip); continue; }
        struct gpiod_line_settings *s = gpiod_line_settings_new();
        struct gpiod_line_config *lc = gpiod_line_config_new();
        struct gpiod_request_config *rc = gpiod_request_config_new();
        gpiod_line_settings_set_direction(s, output ? GPIOD_LINE_DIRECTION_OUTPUT : GPIOD_LINE_DIRECTION_INPUT);
        if (!output && edges) gpiod_line_settings_set_edge_detection(s, GPIOD_LINE_EDGE_BOTH);
        unsigned int o = off;
        gpiod_line_config_add_line_settings(lc, &o, 1, s);
        gpiod_request_config_set_consumer(rc, "latency-echo");
        struct gpiod_line_request *r = gpiod_chip_request_lines(chip, rc, lc);
        if (!r) { perror(name); exit(1); }
        gpiod_request_config_free(rc); gpiod_line_config_free(lc); gpiod_line_settings_free(s);
        *chip_out = chip;
        printf("%s: %s line %d\n", name, path, off);
        return r;
    }
    fprintf(stderr, "no GPIO line named %s (wrong pinmux profile?)\n", name);
    exit(1);
}

int main(int argc, char **argv)
{
    long period_us = 0; int edge_mode = 0;
    if (argc > 1 && strcmp(argv[1], "-e") == 0) edge_mode = 1;
    else if (argc > 1) period_us = atol(argv[1]);

    struct gpiod_chip *ci, *co;
    struct gpiod_line_request *in = request("I0", 0, edge_mode, &ci);
    struct gpiod_line_request *out = request("Q0", 1, 0, &co);
    unsigned int in_off = 0, out_off = 0;
    gpiod_line_request_get_requested_offsets(in, &in_off, 1);
    gpiod_line_request_get_requested_offsets(out, &out_off, 1);

    struct sched_param sp = { .sched_priority = 80 };
    if (sched_setscheduler(0, SCHED_FIFO, &sp) < 0) perror("SCHED_FIFO (continuing without)");
    if (mlockall(MCL_CURRENT | MCL_FUTURE) < 0) perror("mlockall");
    signal(SIGINT, on_sig); signal(SIGTERM, on_sig);
    printf("mode: %s, SCHED_FIFO 80\n", edge_mode ? "edge events" : period_us ? "periodic poll" : "busy poll");

    unsigned long cycles = 0;
    struct gpiod_edge_event_buffer *buf = edge_mode ? gpiod_edge_event_buffer_new(16) : NULL;
    struct timespec next; clock_gettime(CLOCK_MONOTONIC, &next);
    while (!stop) {
        if (edge_mode) {
            if (gpiod_line_request_wait_edge_events(in, 1000000000) <= 0) continue;
            gpiod_line_request_read_edge_events(in, buf, 16);
        } else if (period_us) {
            next.tv_nsec += period_us * 1000;
            while (next.tv_nsec >= 1000000000L) { next.tv_nsec -= 1000000000L; next.tv_sec++; }
            clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next, NULL);
        }
        enum gpiod_line_value v = gpiod_line_request_get_value(in, in_off);
        gpiod_line_request_set_value(out, out_off, v);
        cycles++;
    }
    printf("\n%lu cycles\n", cycles);
    gpiod_line_request_release(in); gpiod_line_request_release(out);
    gpiod_chip_close(ci); gpiod_chip_close(co);
    return 0;
}
