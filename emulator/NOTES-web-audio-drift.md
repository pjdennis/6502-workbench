# Web-audio drift in the wendy2c emulator's web UI

> **Status (2026-09-30): still open.** Checked against `web/wendy2c.js`
> (`playAudioFrame` still has only the one-sided `audioNextTime` resync and no
> AudioWorklet) and `wendy2c_web.c` (8192-sample ring, frames of up to 2000
> samples): section 1 describes the current code and section 3 is not implemented.

Investigation notes on how audio is delivered from the emulator to the
browser, what currently protects (and fails to protect) against drift,
and a sketch of a moderately sophisticated fix. Captured for future
reference — nothing here is implemented yet.

## 1. Current pipeline

### Server → wire

- `audio_step` in `audio.c` is called from the bus/CPU loop and emits one
  int16 sample every `osc_per_sample` emulator oscillator ticks (default
  22050 Hz). Each sample is delivered through three sinks:
  miniaudio's local SPSC ring (when `--live`), the WAV writer (when
  `--wav`), and `tap_cb` — which `emu_wendy2c.c` wires to
  `wendy2c_web_audio_tap`.
- The emulator's main loop in `emu_wendy2c.c` calls `wendy2c_pace`
  before each step. `wendy2c_pace` *only ever sleeps* — it sleeps when
  `emu_ns > wall_ns`, but never tries to catch up if the emulator is
  behind. So the producer is wallclock-paced with a downward bias: at
  most 22050 samples per wallclock second, often slightly fewer on a
  loaded host.
- `wendy2c_web_audio_tap` pushes each sample into a per-server ring
  (`audio_ring`, 8192 int16 = ~370 ms @ 22050 Hz). On overflow it drops
  the oldest sample. Overflow only really happens when no client is
  attached.
- Every ~33 ms (the snapshot cadence — see `SNAP_NS` in
  `emu_wendy2c.c`), `wendy2c_web_flush_audio` drains the ring into one
  or more WebSocket binary frames, each tagged `0x01` followed by
  little-endian int16 samples (capped at 2000 samples per frame in
  `wendy2c_web_broadcast_audio`).
- The WebSocket is TCP, so **once a client is attached, no audio frames
  are dropped on the wire**. Backpressure shows up as growing kernel
  send buffer, then a growing JS receive queue.

### Wire → speakers (`web/wendy2c.js`)

- `handleBinary` unpacks the `0x01` frames into `Int16Array` and calls
  `playAudioFrame`.
- `playAudioFrame` allocates an `AudioBuffer` at `audioRate`, copies the
  samples in (float = int16 / 32768), wraps it in an
  `AudioBufferSourceNode`, and calls `src.start(audioNextTime)`.
- The only correction is the line:

  ```js
  if (audioNextTime < now + 0.02) audioNextTime = now + 0.02; // resync
  ```

  This fires when scheduling has fallen *behind* `now` — i.e., the
  browser has run out of audio — and papers it over with a ~20 ms gap
  by jumping `audioNextTime` forward to "now + 20 ms".

## 2. What stops the page drifting behind?

**Almost nothing — by design, given the producer-side bias.**

- The resync line is **one-sided**: it covers the underrun case
  (browser has nothing to play) but does not bound `audioNextTime - now`
  on the upper side.
- The system stays roughly stable in practice only because
  `wendy2c_pace` biases the producer toward "at most wallclock rate".
  The natural failure mode is therefore underrun → resync gap, which
  the existing line handles (audibly, but bounded).
- The case with **no defense**: if the browser's `AudioContext` clock
  runs slightly slower than the emulator's wallclock (audio device
  drift, exotic hardware, long sessions), the producer outpaces the
  consumer. `audioNextTime` creeps further ahead of `now`, latency
  grows monotonically, and the only ceilings are the TCP send buffer
  and Web Audio's scheduling queue. The page audibly drifts behind the
  emulation with no recovery.

## 3. A moderately sophisticated fix (sketch — not implemented)

Goal: target a small, fixed latency (~80–120 ms) and smoothly converge
back to it without audible gaps or jumps in the common case.

### 3.1. Pick a target latency

`TARGET = 0.10` (100 ms). High enough to absorb the 33 ms server flush
cadence + TCP jitter; low enough that button presses still feel
responsive.

### 3.2. Treat the emulator as the master clock

The audio device is the slave. Instead of scheduling each WS frame at
`audioNextTime`, maintain a single jitter buffer and continuously
resample into the audio device's clock. Drift becomes one observable:

```
lag = ringFillSamples / audioRate
```

`audioNextTime` goes away.

### 3.3. Move playback into an `AudioWorkletNode`

- One persistent worklet, fed by a ring buffer that the WS handler
  writes into.
- The worklet pulls 128-sample blocks at the audio device's actual
  rate.
- Replaces the per-frame `AudioBufferSourceNode` churn with a steady
  pull model — also better for the GC and the scheduler.

### 3.4. Smooth rate correction

- Maintain an EWMA of `lag` over ~300 ms (ignore the per-frame jitter).
- Error `e = lag_ewma - TARGET`.
- Inside the worklet, resample the ring → device at a tweaked ratio:

  ```
  rate = 1.0 + clamp(k * e, -0.005, +0.005)
  ```

  i.e., consume the ring 0.5 % faster (when lag is high) or slower
  (when lag is low) than nominal. Low-pass the `rate` itself so it
  changes over hundreds of ms, not instantly.
- A 0.5 % pitch shift is ~9 cents — well below most listeners'
  perceptual floor, and inaudible on a piezo buzz.

### 3.5. Two safety nets framing the smooth band

- **Underrun (ring empty):** emit silence for the missing samples and
  let the smooth controller pull `lag` back up. Do **not** jump
  `audioNextTime` forward — that trades a gap now for accumulated lag
  later (today's behaviour).
- **Runaway (`lag > ~3 × TARGET`):** the controller can't recover in
  reasonable time, so drop a chunk in one shot — but at a zero
  crossing with a short equal-power crossfade, so it's a click rather
  than a pop.

### 3.6. Optional refinements

- Use WebSocket frame arrival timestamps to estimate the producer's
  effective rate (~30 frames/s × known sample count). Gives the
  controller a feed-forward term so it doesn't have to discover drift
  purely from `lag` excursions.
- Expose `lag` and the controller's current rate in the UI as a small
  diagnostic readout — cheap, very useful when tuning.

## 4. Tradeoffs vs. the existing 3-line scheme

| | Current resync | Proposed |
|--|--|--|
| Lines of JS | ~3 | ~150 |
| Audible failure mode | ~20 ms gap on underrun | None in the smooth band; occasional crossfaded click only under runaway |
| Bounded latency | Lower bound only (`now + 0.02`) | Both sides, around `TARGET` |
| Recovers from AudioContext clock drift | No | Yes |
| Steady-state pitch impact | None | ≤ 0.005 (≤ ~9 cents); inaudible |
| Complexity | Trivial | Real controller; needs tuning |

The current scheme is fine as long as `wendy2c_pace`'s downward bias
keeps the system in the underrun regime. The moment AudioContext drift
dominates (long sessions, audio device running slow), it falls apart
with no recovery — and that's exactly the case the proposed design
targets.
