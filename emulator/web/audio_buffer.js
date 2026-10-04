// The audio jitter buffer between the WebSocket and the sound card,
// for audio_worklet.js (an ES module, so tests can import it too).
//
// The emulator sends its samples in ~33 ms frames; they reach the page
// with network and main-thread jitter (in a background tab, in bursts).
// The audio thread pulls them in 128-frame blocks at the sound card's
// rate. The buffer:
//   - holds about `target` seconds: MARGIN more than the longest wait
//     between deliveries it sees (raised as soon as it sees it), so a
//     steady 33 ms stream sits at about MARGIN + 33 ms;
//   - plays them resampled to the sound card's rate, at up to MAX_TRIM
//     (0.5%, inaudible) faster or slower to keep the fill at the target,
//     so the emulator's and the sound card's clocks needn't agree;
//   - on an underrun plays silence, raises the target by half, and waits
//     until it has the target before playing again;
//   - lowers the target again by SHRINK after STEADY seconds without one
//     in which the fill never fell below half the target (bursts still
//     need it, a past stall doesn't);
//   - drops a backlog of more than BACKLOG seconds over the target.

const MARGIN = 0.12;          // s
const MAX_TARGET = 1.5;       // s
const MAX_TRIM = 0.005;       // the most the playback rate moves from nominal
const GAIN = 0.1;             // rate trim per second of fill error
const FILL_SMOOTHING = 0.3;   // s: the fill's moving average
const RATE_SMOOTHING = 0.5;   // s: how fast the rate follows the trim
const STEADY = 10;            // s
const SHRINK = 0.8;
const BACKLOG = 1.5;          // s
const CAPACITY = 4;           // s of source samples held at most

export class JitterBuffer {
  constructor(sourceRate, outputRate) {
    this.sourceRate = sourceRate;
    this.outputRate = outputRate;
    this.ring = new Float32Array(Math.ceil(sourceRate * CAPACITY));
    this.read = 0;              // ring index of the oldest sample
    this.count = 0;             // samples held
    this.pos = 0;               // fractional position past `read` of the next output sample
    this.target = MARGIN;
    this.average = 0;           // the fill's moving average, s
    this.rate = 1;              // playback rate trim
    this.priming = true;        // waiting for the target before playing
    this.time = 0;              // s of output so far: the buffer's clock
    this.lastPush = null;       // when samples last came
    this.steady = 0;            // s since the last underrun or shrink
    this.lowest = Infinity;     // the lowest fill in that time, s
    this.underruns = 0;
    this.drops = 0;
  }

  setSourceRate(rate) {
    if (rate === this.sourceRate) return;
    this.sourceRate = rate;
    this.ring = new Float32Array(Math.ceil(rate * CAPACITY));
    this.read = this.count = this.pos = 0;
    this.priming = true;
  }

  fill() {
    return Math.max(0, this.count - this.pos) / this.sourceRate;
  }

  push(samples) {
    if (this.lastPush !== null) {
      const wait = this.time - this.lastPush;
      if (wait + MARGIN > this.target) this.target = Math.min(MAX_TARGET, wait + MARGIN);
    }
    this.lastPush = this.time;
    const ring = this.ring, n = ring.length;
    for (let i = 0; i < samples.length; i++) {
      if (this.count === n) { this.read = (this.read + 1) % n; this.count--; }   // full: drop the oldest
      ring[(this.read + this.count) % n] = samples[i];
      this.count++;
    }
    if (this.fill() > this.target + BACKLOG) {
      this.consume(this.count - Math.round(this.target * this.sourceRate));
      this.pos = 0;
      this.average = this.fill();
      this.drops++;
    }
  }

  consume(k) {
    this.read = (this.read + k) % this.ring.length;
    this.count -= k;
  }

  // Fill `out` with the next block for the sound card.
  pull(out) {
    const block = out.length / this.outputRate;
    this.time += block;
    if (this.priming && !this.primed()) { out.fill(0); return; }

    const fill = this.fill();
    this.steady += block;
    this.lowest = Math.min(this.lowest, fill);
    if (this.steady >= STEADY) {
      if (this.lowest > this.target / 2) this.target = Math.max(MARGIN, this.target * SHRINK);
      this.steady = 0;
      this.lowest = Infinity;
    }

    // Steer the rate to keep the fill at the target.
    this.average += (fill - this.average) * Math.min(1, block / FILL_SMOOTHING);
    const trim = Math.max(-MAX_TRIM, Math.min(MAX_TRIM, GAIN * (this.average - this.target)));
    this.rate += (1 + trim - this.rate) * Math.min(1, block / RATE_SMOOTHING);
    const step = this.sourceRate / this.outputRate * this.rate;

    const ring = this.ring, n = ring.length;
    for (let i = 0; i < out.length; i++) {
      const whole = Math.floor(this.pos);
      if (whole + 1 >= this.count) {       // out of samples: an underrun
        out.fill(0, i);
        this.underruns++;
        this.priming = true;
        this.target = Math.min(MAX_TARGET, this.target * 1.5);
        this.steady = 0;
        this.lowest = Infinity;
        break;
      }
      const frac = this.pos - whole;
      const a = ring[(this.read + whole) % n], b = ring[(this.read + whole + 1) % n];
      out[i] = a + (b - a) * frac;
      this.pos += step;
    }
    const used = Math.min(Math.floor(this.pos), this.count);
    this.consume(used);
    this.pos -= used;
  }

  // While priming: start playing once the target is held.
  primed() {
    if (this.fill() < this.target) return false;
    this.priming = false;
    this.average = this.fill();
    return true;
  }

  stats() {
    return { fill: this.fill(), target: this.target, rate: this.rate,
             underruns: this.underruns, drops: this.drops, priming: this.priming };
  }
}
