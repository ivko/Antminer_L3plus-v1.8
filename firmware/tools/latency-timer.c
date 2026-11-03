/* Timer wake-up latency, cyclictest-style, for comparing kernels (docs/10-latency.md).
 * A SCHED_FIFO 80 thread sleeps with clock_nanosleep(TIMER_ABSTIME) for a fixed period and
 * measures how late it wakes up. No GPIO, no wiring: this is the scheduler + timer path only.
 *
 *   gcc -O2 -o latency-timer latency-timer.c
 *   ./latency-timer [seconds=60] [period_us=1000]
 * prints min / mean / p99 / p99.9 / max in us and a coarse histogram.
 */
#define _GNU_SOURCE
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

#define HIST_US 20000
static volatile int stop;
static void on_sig(int s) { (void)s; stop = 1; }

int main(int argc, char **argv)
{
    long seconds = argc > 1 ? atol(argv[1]) : 60;
    long period_us = argc > 2 ? atol(argv[2]) : 1000;
    static unsigned long hist[HIST_US + 1];
    struct sched_param sp = { .sched_priority = 80 };
    if (sched_setscheduler(0, SCHED_FIFO, &sp) < 0) perror("SCHED_FIFO (continuing without)");
    if (mlockall(MCL_CURRENT | MCL_FUTURE) < 0) perror("mlockall");
    signal(SIGINT, on_sig); signal(SIGTERM, on_sig);

    struct timespec next, now;
    clock_gettime(CLOCK_MONOTONIC, &next);
    long long end = (next.tv_sec + seconds) * 1000000000LL + next.tv_nsec;
    long min = 1L << 30, max = 0; double sum = 0; unsigned long n = 0, over = 0;
    while (!stop) {
        next.tv_nsec += period_us * 1000;
        while (next.tv_nsec >= 1000000000L) { next.tv_nsec -= 1000000000L; next.tv_sec++; }
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next, NULL);
        clock_gettime(CLOCK_MONOTONIC, &now);
        long long t = (now.tv_sec - next.tv_sec) * 1000000000LL + (now.tv_nsec - next.tv_nsec);
        long us = (long)(t / 1000);
        if (us < 0) us = 0;
        if (us < min) min = us;
        if (us > max) max = us;
        sum += us; n++;
        if (us > HIST_US) { hist[HIST_US]++; over++; } else hist[us]++;
        if (now.tv_sec * 1000000000LL + now.tv_nsec >= end) break;
        /* if we are more than one period late, resynchronise instead of spinning to catch up */
        if (us > period_us) { clock_gettime(CLOCK_MONOTONIC, &next); }
    }
    unsigned long acc = 0; long p99 = -1, p999 = -1;
    for (long i = 0; i <= HIST_US; i++) {
        acc += hist[i];
        if (p99 < 0 && acc >= n * 0.99) p99 = i;
        if (p999 < 0 && acc >= n * 0.999) p999 = i;
    }
    printf("period %ld us, %lu wake-ups: min %ld us, mean %.1f us, p99 %ld us, p99.9 %ld us, max %ld us\n",
           period_us, n, min, n ? sum / n : 0, p99, p999, max);
    printf("histogram (us: count):");
    static const long edges[] = { 10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 5000, HIST_US };
    long lo = 0;
    for (unsigned k = 0; k < sizeof edges / sizeof *edges; k++) {
        unsigned long c = 0;
        for (long i = lo; i < edges[k] && i <= HIST_US; i++) c += hist[i];
        if (c) printf(" %ld-%ld:%lu", lo, edges[k], c);
        lo = edges[k];
    }
    if (over) printf(" >%d:%lu", HIST_US, over);
    printf("\n");
    return 0;
}
