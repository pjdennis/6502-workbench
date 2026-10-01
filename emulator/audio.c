/* wendy2c PB7 audio: per-sample averaging, piezo high-pass, WAV writer and miniaudio live playback (see audio.h). */
#include "audio.h"

#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

/* Pull in miniaudio's implementation. We only need playback + the
 * device APIs; trim what we can to keep the binary lean. */
#define MA_NO_DECODING
#define MA_NO_ENCODING
#define MA_NO_GENERATION
#define MA_IMPLEMENTATION
#include "vendor/miniaudio.h"

/* ---- ring buffer (single-producer single-consumer) ----
 * The hot path (audio_step) is the producer; miniaudio's data
 * callback (running on its own audio thread) is the consumer. */

#define RB_CAPACITY 16384  /* int16 samples; ~0.7 sec @ 22050 Hz */

struct live_state {
    ma_device device;
    ma_device_config config;

    /* SPSC ring of int16 samples. */
    int16_t buf[RB_CAPACITY];
    _Atomic unsigned int head;  /* producer writes */
    _Atomic unsigned int tail;  /* consumer reads */

    /* Stat counters (for debug; harmless if unread). */
    unsigned long long drops;       /* producer hit full ring */
    unsigned long long underruns;   /* consumer hit empty ring */
};

static void rb_push(struct live_state *l, int16_t sample) {
    unsigned int h = atomic_load_explicit(&l->head, memory_order_relaxed);
    unsigned int t = atomic_load_explicit(&l->tail, memory_order_acquire);
    if (h - t >= RB_CAPACITY) {
        l->drops++;
        return;
    }
    l->buf[h % RB_CAPACITY] = sample;
    atomic_store_explicit(&l->head, h + 1, memory_order_release);
}

static unsigned int rb_pop_into(struct live_state *l,
                                int16_t *dst, unsigned int n) {
    unsigned int h = atomic_load_explicit(&l->head, memory_order_acquire);
    unsigned int t = atomic_load_explicit(&l->tail, memory_order_relaxed);
    unsigned int have = h - t;
    unsigned int take = have < n ? have : n;
    for (unsigned int i = 0; i < take; i++) {
        dst[i] = l->buf[(t + i) % RB_CAPACITY];
    }
    atomic_store_explicit(&l->tail, t + take, memory_order_release);
    return take;
}

static void live_data_callback(ma_device *device, void *output,
                               const void *input, ma_uint32 frame_count) {
    (void)input;
    struct live_state *l = (struct live_state *)device->pUserData;
    int16_t *out = (int16_t *)output;
    unsigned int got = rb_pop_into(l, out, frame_count);
    if (got < frame_count) {
        /* Underrun: fill the rest with silence. */
        memset(out + got, 0, (frame_count - got) * sizeof(int16_t));
        l->underruns++;
    }
}

/* ---- WAV writer ----
 * Standard 44-byte PCM-mono int16 header; data size is fixed up on
 * close so the file is valid even after Ctrl-C. */

static void wav_write_u16_le(FILE *f, uint16_t v) {
    uint8_t b[2] = { (uint8_t)v, (uint8_t)(v >> 8) };
    fwrite(b, 1, 2, f);
}
static void wav_write_u32_le(FILE *f, uint32_t v) {
    uint8_t b[4] = { (uint8_t)v, (uint8_t)(v >> 8),
                     (uint8_t)(v >> 16), (uint8_t)(v >> 24) };
    fwrite(b, 1, 4, f);
}

static int wav_write_header(FILE *f, int sample_rate) {
    if (fwrite("RIFF", 1, 4, f) != 4) return -1;
    wav_write_u32_le(f, 0);          /* RIFF chunk size, fixed up later */
    fwrite("WAVE", 1, 4, f);
    fwrite("fmt ", 1, 4, f);
    wav_write_u32_le(f, 16);         /* fmt chunk size */
    wav_write_u16_le(f, 1);          /* PCM */
    wav_write_u16_le(f, 1);          /* mono */
    wav_write_u32_le(f, (uint32_t)sample_rate);
    wav_write_u32_le(f, (uint32_t)(sample_rate * 2));  /* byte rate */
    wav_write_u16_le(f, 2);          /* block align */
    wav_write_u16_le(f, 16);         /* bits per sample */
    fwrite("data", 1, 4, f);
    wav_write_u32_le(f, 0);          /* data size, fixed up later */
    return 0;
}

static void wav_fixup_sizes(FILE *f, uint32_t samples) {
    uint32_t data_bytes = samples * 2;
    uint32_t riff_size = 36 + data_bytes;
    fflush(f);
    if (fseek(f, 4, SEEK_SET) == 0) wav_write_u32_le(f, riff_size);
    if (fseek(f, 40, SEEK_SET) == 0) wav_write_u32_le(f, data_bytes);
    fflush(f);
}

/* ---- core: init / step / close ---- */

int audio_init(struct audio_state *a,
               int sample_rate,
               const char *wav_path,
               int enable_live,
               double osc_per_us) {
    memset(a, 0, sizeof(*a));
    if (sample_rate <= 0) sample_rate = AUDIO_DEFAULT_SAMPLE_RATE;
    a->sample_rate = sample_rate;
    a->osc_per_sample = osc_per_us * 1.0e6 / (double)sample_rate;

    /* 1st-order HP at f_c = 500 Hz, alpha = RC/(RC+dt). */
    const double fc = 500.0;
    double dt = 1.0 / (double)sample_rate;
    double rc = 1.0 / (2.0 * M_PI * fc);
    a->hp_alpha = rc / (rc + dt);

    int any = 0;

    if (wav_path) {
        a->wav_file = fopen(wav_path, "wb");
        if (!a->wav_file) {
            fprintf(stderr, "audio: could not open WAV path '%s' for writing\n",
                    wav_path);
        } else if (wav_write_header(a->wav_file, sample_rate) != 0) {
            fprintf(stderr, "audio: failed to write WAV header to '%s'\n",
                    wav_path);
            fclose(a->wav_file);
            a->wav_file = NULL;
        } else {
            fprintf(stderr, "audio: writing WAV to %s @ %d Hz\n",
                    wav_path, sample_rate);
            any = 1;
        }
    }

    if (enable_live) {
        struct live_state *l = (struct live_state *)calloc(1, sizeof(*l));
        if (!l) {
            fprintf(stderr, "audio: out of memory\n");
        } else {
            l->config = ma_device_config_init(ma_device_type_playback);
            l->config.playback.format = ma_format_s16;
            l->config.playback.channels = 1;
            l->config.sampleRate = (ma_uint32)sample_rate;
            l->config.dataCallback = live_data_callback;
            l->config.pUserData = l;
            if (ma_device_init(NULL, &l->config, &l->device) != MA_SUCCESS) {
                fprintf(stderr, "audio: ma_device_init failed (no audio device?)\n");
                free(l);
            } else if (ma_device_start(&l->device) != MA_SUCCESS) {
                fprintf(stderr, "audio: ma_device_start failed\n");
                ma_device_uninit(&l->device);
                free(l);
            } else {
                ma_backend backend = l->device.pContext->backend;
                const char *backend_name = ma_get_backend_name(backend);
                if (backend == ma_backend_null) {
                    fprintf(stderr,
                            "audio: warning -- no real audio backend available; "
                            "miniaudio selected the Null backend, so --audio is a no-op. "
                            "Install PulseAudio/PipeWire/ALSA (Linux/WSL), or run on a "
                            "host with native audio (macOS/Windows/WSLg).\n");
                } else {
                    fprintf(stderr, "audio: live playback via %s @ %d Hz\n",
                            backend_name ? backend_name : "?", sample_rate);
                }
                a->live = l;
                any = 1;
            }
        }
    }

    a->enabled = any;
    return any ? 0 : (wav_path || enable_live ? 1 : 0);
}

static int16_t saturate_i16(double v) {
    if (v >  32767.0) return  32767;
    if (v < -32768.0) return -32768;
    return (int16_t)v;
}

static void emit_sample(struct audio_state *a) {
    /* Mean level over the audio-sample period: 0..1 from PB7 toggles. */
    double avg = (a->time_accum > 0.0) ? (a->level_accum / a->time_accum) : 0.0;

    /* Piezo HP: y[n] = alpha * (y[n-1] + x[n] - x[n-1]). Centers the
     * signal on 0 and gives the piezo's characteristic "buzzy" sound
     * by suppressing energy below ~500 Hz. */
    double y = a->hp_alpha * (a->hp_y_prev + avg - a->hp_x_prev);
    a->hp_x_prev = avg;
    a->hp_y_prev = y;

    /* Scale to int16. The HP-filtered square-wave is bounded roughly
     * in [-1, 1]; we scale by 0x4000 to leave headroom and avoid harsh
     * clipping. */
    int16_t s = saturate_i16(y * 16384.0);

    if (a->wav_file) {
        uint8_t b[2] = { (uint8_t)s, (uint8_t)((uint16_t)s >> 8) };
        fwrite(b, 1, 2, a->wav_file);
        a->wav_samples_written++;
    }
    if (a->live) {
        rb_push((struct live_state *)a->live, s);
    }
    if (a->tap_cb) {
        a->tap_cb(a->tap_user, s);
    }

    /* Carry over the fractional remainder so timing stays exact. */
    a->time_accum  -= a->osc_per_sample;
    a->level_accum  = avg * a->time_accum;  /* preserve the bias of the leftover */
}

void audio_set_tap(struct audio_state *a,
                   void (*cb)(void *user, int16_t sample),
                   void *user) {
    if (!a) return;
    a->tap_cb = cb;
    a->tap_user = user;
    if (cb) a->enabled = 1;  /* tap on => keep emit_sample running */
}

void audio_step(struct audio_state *a, uint64_t osc_ticks, uint8_t portb_pins) {
    if (!a->enabled) return;
    uint64_t dt = osc_ticks - a->last_osc;
    if (dt == 0) return;
    a->last_osc = osc_ticks;
    double level = (portb_pins & 0x80) ? 1.0 : 0.0;
    a->level_accum += level * (double)dt;
    a->time_accum  += (double)dt;
    while (a->time_accum >= a->osc_per_sample) {
        emit_sample(a);
    }
}

void audio_close(struct audio_state *a) {
    if (!a) return;
    if (a->live) {
        struct live_state *l = (struct live_state *)a->live;
        ma_device_uninit(&l->device);
        free(l);
        a->live = NULL;
    }
    if (a->wav_file) {
        wav_fixup_sizes(a->wav_file, a->wav_samples_written);
        fclose(a->wav_file);
        a->wav_file = NULL;
    }
    a->enabled = 0;
}
