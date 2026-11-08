// The microphone's sound for voice.js, a block at a time (about 40 ms). A worklet runs apart from
// the page, so it lives in a file of its own; it only collects samples and hands them on.
class Ear extends AudioWorkletProcessor {
  constructor() {
    super();
    this.block = new Float32Array(2048);
    this.n = 0;
  }

  process(inputs) {
    const samples = inputs[0]?.[0];
    if (samples) {
      for (let i = 0; i < samples.length; i++) {
        this.block[this.n++] = samples[i];
        if (this.n === this.block.length) {
          this.port.postMessage(this.block, [this.block.buffer]);
          this.block = new Float32Array(2048);
          this.n = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('arnheim-ear', Ear);
