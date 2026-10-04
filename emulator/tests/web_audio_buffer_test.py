#!/usr/bin/env python3
"""Unit tests for the web page's audio jitter buffer (emulator/web/audio_buffer.js).

The buffer sits between the WebSocket, which delivers the emulator's
samples in ~33 ms frames with network and main-thread jitter, and the
audio thread, which pulls 128-frame blocks at the sound card's rate. It
must play steadily through jitter, grow its latency target to cover
long waits between deliveries (as when a background tab gets its
messages in bursts) and shrink it back when things are steady, follow a producer slightly slower
or faster than the sound card by playing up to 0.5% slower or faster,
recover from a stall, and drop a backlog it can't work off.

Each case simulates time deterministically: the module is loaded into a
headless Chromium page (it is an ES module the AudioWorklet imports) and
driven with simulated frame arrivals and block pulls. No emulator needed.
"""

import functools
import http.server
import threading

from web_test_util import REPO_ROOT, failed, main, passed, skipped

# Runs one simulation in the page: frames of `frame` samples produced at
# `rate` x the nominal 22050 Hz, each delivered at its production time
# plus a delay from `delay(i)` (seconds; in arrival order), and pulled in
# 128-frame blocks at `outRate`. Returns the buffer's stats, sampled
# once a second, and its final stats.
SIMULATE = """async ({ seconds, outRate, rate, delays, stallFrom, stallTo, flood }) => {
    const { JitterBuffer } = await import('/audio_buffer.js');
    const SRC = 22050, FRAME = 735, BLOCK = 128;
    const buf = new JitterBuffer(SRC, outRate);
    const frames = [];
    for (let i = 0, t = 0; t < seconds; i++, t = i * FRAME / (SRC * rate)) {
        if (t >= stallFrom && t < stallTo) continue;
        const arrive = Math.max(t + delays[i % delays.length], frames.length ? frames[frames.length - 1].arrive : 0);
        const samples = new Float32Array(FRAME);
        for (let k = 0; k < FRAME; k++) samples[k] = Math.sin(2 * Math.PI * 440 * (i * FRAME + k) / SRC);
        frames.push({ arrive, samples });
    }
    if (flood) frames.unshift({ arrive: 0, samples: new Float32Array(SRC * flood) });
    const out = new Float32Array(BLOCK);
    const timeline = [];
    let next = 0, nextSecond = 1;
    for (let t = 0; t < seconds; t += BLOCK / outRate) {
        while (next < frames.length && frames[next].arrive <= t) buf.push(frames[next++].samples);
        buf.pull(out);
        if (t >= nextSecond) { timeline.push(buf.stats()); nextSecond++; }
    }
    return { timeline, final: buf.stats() };
}"""

# Delays: up to 80 ms of jitter, deterministic.
JITTER = [((i * 37) % 17) / 16 * 0.08 for i in range(101)]
# Background tab: messages held and delivered once a second.
BURSTS = [1.0 - (i % 30) / 30 for i in range(30)]


def cases(page):
    """Yields (name, problem or None) for each case."""
    def run(seconds=30, outRate=48000, rate=1.0, delays=(0,), stallFrom=-1, stallTo=-1, flood=0):
        return page.evaluate(SIMULATE, dict(seconds=seconds, outRate=outRate, rate=rate, delays=list(delays),
                                            stallFrom=stallFrom, stallTo=stallTo, flood=flood))

    r = run(outRate=48000)
    fills = [s["fill"] for s in r["timeline"][5:]]
    yield "steady stream at 48 kHz plays without gaps near the base target", (
        None if r["final"]["underruns"] == 0 and all(0.05 <= f <= 0.25 for f in fills)
        else f"{r['final']}, fills {fills}")

    r = run(outRate=22050)
    yield "steady stream at 22050 Hz plays without gaps", (
        None if r["final"]["underruns"] == 0 else f"{r['final']}")

    r = run(delays=JITTER)
    yield "80 ms of network jitter plays without gaps", (
        None if r["final"]["underruns"] == 0 else f"{r['final']}")

    r = run(seconds=60, delays=BURSTS)
    late = [s["underruns"] for s in r["timeline"][30:]]
    yield "once-a-second bursts: a few gaps, then the target grows to cover them", (
        None if r["final"]["underruns"] <= 3 and late[0] == late[-1]
        else f"{r['final']}, underruns over the last 30 s {late}")

    steady = run(seconds=60)["final"]["target"]
    r = run(seconds=180, stallFrom=5, stallTo=5.6)
    yield "a stall is one gap, and the target shrinks back once things are steady", (
        None if r["final"]["underruns"] == 1 and r["final"]["target"] <= steady + 0.001
        else f"{r['final']}; a steady stream's target is {steady}")

    for rate in (0.997, 1.003):
        r = run(seconds=90, rate=rate)
        fills = [s["fill"] for s in r["timeline"][30:]]
        yield f"a producer at {rate}x the sound card's rate is followed without gaps", (
            None if r["final"]["underruns"] == 0 and r["final"]["drops"] == 0 and all(0.05 <= f <= 0.25 for f in fills)
            else f"{r['final']}, fills {fills}")

    r = run(seconds=10, flood=3)
    yield "a 3 s backlog is dropped back to the target", (
        None if r["final"]["drops"] >= 1 and r["final"]["fill"] <= 0.25
        else f"{r['final']}")


def run_test(verbose=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return skipped("audio buffer test (playwright not installed)")
    web = REPO_ROOT / "emulator" / "web"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    problems = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            # Any page from the web directory, for a same-origin import.
            page.goto(f"http://127.0.0.1:{server.server_port}/board.css")
            for name, problem in cases(page):
                if verbose or problem: print(f"  {'FAIL' if problem else 'ok  '} {name}" + (f": {problem}" if problem else ""))
                if problem: problems.append(name)
            browser.close()
    finally:
        server.shutdown()
    if problems:
        return failed(f"audio buffer test: {len(problems)} case(s) failed")
    return passed("audio buffer test")


if __name__ == "__main__":
    main("web audio jitter buffer test (Playwright)", run_test)
