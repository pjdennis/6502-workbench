// The page's audio, on the browser's audio thread: an AudioWorklet that
// plays the emulator's samples through the jitter buffer
// (audio_buffer.js). Board.js posts {rate} and {samples: Float32Array};
// the worklet posts the buffer's stats about four times a second.
// Running here, playback doesn't depend on the page's main thread, which
// a background tab or a busy page can hold up.

import { JitterBuffer } from "./audio_buffer.js";

class BoardAudio extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new JitterBuffer(22050, sampleRate);
    this.sinceReport = 0;
    this.port.onmessage = (e) => {
      if (e.data.rate) this.buffer.setSourceRate(e.data.rate);
      if (e.data.samples) this.buffer.push(e.data.samples);
    };
  }

  process(inputs, outputs) {
    const channels = outputs[0];
    this.buffer.pull(channels[0]);
    for (let c = 1; c < channels.length; c++) channels[c].set(channels[0]);
    this.sinceReport += channels[0].length;
    if (this.sinceReport >= sampleRate / 4) {
      this.sinceReport = 0;
      this.port.postMessage(this.buffer.stats());
    }
    return true;
  }
}

registerProcessor("board-audio", BoardAudio);
