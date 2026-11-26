// SPDX-License-Identifier: Apache-2.0
// One bounded integer workload on a selected CPU. No governor/thermal writes.
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

static double now(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(2); }
    return t.tv_sec + t.tv_nsec / 1e9;
}

static long argument(const char *s) {
    char *end;
    errno = 0;
    long n = strtol(s, &end, 10);
    if (errno || !*s || *end) { fprintf(stderr, "Invalid integer\n"); exit(2); }
    return n;
}

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "Usage: cpu-policy-load CPU SECONDS\n"); return 2; }
    long cpu = argument(argv[1]), seconds = argument(argv[2]);
    if (cpu < 0 || cpu > 7 || seconds < 1 || seconds > 8) return 2;
    cpu_set_t mask, actual;
    CPU_ZERO(&mask);
    CPU_SET(cpu, &mask);
    if (sched_setaffinity(0, sizeof(mask), &mask) ||
        sched_getaffinity(0, sizeof(actual), &actual)) { perror("affinity"); return 2; }
    if (!CPU_EQUAL(&mask, &actual)) { fprintf(stderr, "Affinity not honored\n"); return 2; }
    // Bound execution even if the host disappears. Android timeout adds a
    // second independent bound when this program is used by the recorder.
    alarm((unsigned)seconds + 2);
    double start = now(), end;
    uint64_t x = UINT64_C(0x9e3779b97f4a7c15), iterations = 0;
    do {
        for (unsigned j = 0; j < 4096; j++) {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
        }
        iterations += 4096;
        end = now();
    } while (end - start < seconds);
    struct rusage usage;
    if (getrusage(RUSAGE_SELF, &usage)) { perror("getrusage"); return 2; }
    double cpu_time = usage.ru_utime.tv_sec + usage.ru_utime.tv_usec / 1e6 +
                      usage.ru_stime.tv_sec + usage.ru_stime.tv_usec / 1e6;
    printf("{\"cpu\":%ld,\"seconds\":%.6f,\"cpu_seconds\":%.6f,"
           "\"iterations\":%" PRIu64 ",\"checksum\":\"%016" PRIx64 "\","
           "\"last_cpu\":%d,\"affinity_verified\":true}\n",
           cpu, end - start, cpu_time, iterations, x, sched_getcpu());
    return 0;
}
