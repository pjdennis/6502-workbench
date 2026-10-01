/* E6502_TRACE diagnostics: PC ring buffer and hottest-PC histogram (see trace.h). */
#include "trace.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int trace_mode = 0;
static uint16_t trace_ring[TRACE_RING_SIZE];
static uint64_t trace_ring_pos = 0;
static uint32_t *trace_hist = NULL;

void trace_init_from_env(void) {
    const char *t = getenv("E6502_TRACE");
    if (t) {
        if (strstr(t, "both") || (strstr(t, "ring") && strstr(t, "hist"))) trace_mode = 3;
        else if (strstr(t, "hist")) trace_mode = 2;
        else if (strstr(t, "ring")) trace_mode = 1;
    }
}

void trace_set_mode(int mode) {
    trace_mode = mode;
}

void trace_reset(void) {
    trace_mode = 0;
    trace_ring_pos = 0;
    if (trace_hist) {
        free(trace_hist);
        trace_hist = NULL;
    }
}

void trace_record(uint16_t cur_pc) {
    if (trace_mode & 1) {
        trace_ring[trace_ring_pos & (TRACE_RING_SIZE - 1)] = cur_pc;
        trace_ring_pos++;
    }
    if (trace_mode & 2) {
        if (trace_hist == NULL) {
            trace_hist = (uint32_t *)calloc(65536, sizeof(uint32_t));
        }
        if (trace_hist) trace_hist[cur_pc]++;
    }
}

static int hist_cmp(const void *a, const void *b) {
    uint32_t ai = *(const uint32_t *)a;
    uint32_t bi = *(const uint32_t *)b;
    if (trace_hist[bi] > trace_hist[ai]) return 1;
    if (trace_hist[bi] < trace_hist[ai]) return -1;
    return 0;
}

void trace_dump(const char *why) {
    if (trace_mode & 1) {
        uint64_t start = trace_ring_pos > TRACE_RING_SIZE
                         ? trace_ring_pos - TRACE_RING_SIZE : 0;
        uint64_t shown = trace_ring_pos - start;
        if (shown > 256) { start = trace_ring_pos - 256; shown = 256; }
        fprintf(stderr, "\n=== trace ring (%s; last %llu PCs) ===\n",
                why, (unsigned long long)shown);
        for (uint64_t i = start; i < trace_ring_pos; i++) {
            fprintf(stderr, " %04X", trace_ring[i & (TRACE_RING_SIZE - 1)]);
            if ((i - start + 1) % 16 == 0) fprintf(stderr, "\n");
        }
        if (shown % 16 != 0) fprintf(stderr, "\n");
    }
    if ((trace_mode & 2) && trace_hist) {
        uint32_t indices[65536];
        int n = 0;
        for (int i = 0; i < 65536; i++) {
            if (trace_hist[i]) indices[n++] = (uint32_t)i;
        }
        qsort(indices, n, sizeof(uint32_t), hist_cmp);
        int show = n > 32 ? 32 : n;
        fprintf(stderr, "\n=== trace hist (%s; top %d of %d distinct PCs) ===\n",
                why, show, n);
        for (int i = 0; i < show; i++) {
            fprintf(stderr, "  %04X  %u\n", indices[i], trace_hist[indices[i]]);
        }
    }
}

uint64_t trace_ring_position(void) {
    return trace_ring_pos;
}

uint16_t trace_ring_at(uint64_t logical_pos) {
    return trace_ring[logical_pos & (TRACE_RING_SIZE - 1)];
}

uint32_t trace_hist_count(uint16_t pc) {
    return trace_hist ? trace_hist[pc] : 0;
}
