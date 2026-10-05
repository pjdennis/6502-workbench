// Board web UI: one page for every machine. The server's first message
// names the machine ({"type":"hello","machine":...}), and the page
// builds itself from that machine's description (machines.js): title,
// LEDs, controls and VIA pin labels. Then: state via WS JSON, audio via
// WS binary, the LCD as a per-pixel canvas render, the LEDs, the pin
// table, the reset button and the status line. Glyphs come from the
// HD44780 ROM Code A00 font (extracted from the datasheet — see
// hd44780_a00_font.js). CGRAM patterns ride along in each state
// snapshot. In 5x10 mode the LCD reports f5x10:1 and we render 10-row
// glyphs with the cursor on row 10; CGRAM slots 0..3 each cover 11
// bytes (10 dot rows + cursor). A machine with a graphic display
// (michael's ILI9341) also gets its frame memory as binary deltas, and
// draws the glass from it.
//
// Board.define(name, description) adds a machine; Board.start() connects.

window.Board = (() => {
  const $ = (id) => document.getElementById(id);

  // ===== HD44780 A00 font (loaded from hd44780_a00_font.js) =====
  const FONT5X8 = window.HD44780_A00.font5x8;     // 256*8 bytes
  const FONT5X10 = window.HD44780_A00.font5x10;   // 32*10 bytes

  function rom5x8(code) {
    // 8 bytes; each byte's low 5 bits are the dot row (bit 4 = leftmost).
    const off = (code & 0xFF) * 8;
    return FONT5X8.subarray(off, off + 8);
  }
  function rom5x10(code) {
    // Defined only for codes 0xE0..0xFF; outside that range fall back
    // to the 5x8 glyph with two empty descender rows.
    if (code >= 0xE0 && code <= 0xFF) {
      const off = (code - 0xE0) * 10;
      return FONT5X10.subarray(off, off + 10);
    }
    const r = rom5x8(code);
    const out = new Uint8Array(10);
    for (let i = 0; i < 8; i++) out[i] = r[i];
    return out;
  }

  // ===== LCD render =====
  const DOT = 3;           // each "pixel" is 3x3 css pixels
  const GAP = 1;           // 1 px gap between pixels
  const COLS_PER_CHAR = 5;
  const CELL_PAD_X = 2;    // 2 dots between adjacent character cells
  const CELL_PAD_Y = 2;    // 2 dots between LCD lines
  const LCD_MARGIN = 8;    // px around the whole grid inside the canvas

  function glyphFor(code, cgram, font5x10) {
    // Returns a Uint8Array of length rows*5, one byte per dot
    // (0 or 1). CGRAM hits codes 0x00..0x0F (lower 4 bits matter).
    const rows = font5x10 ? 10 : 8;
    const bitmap = new Uint8Array(COLS_PER_CHAR * rows);
    const isCgram = code <= 0x0F;
    let glyph;
    if (isCgram) {
      if (font5x10) {
        // 4 slots of 11 bytes (10 dot rows; the 11th is the cursor
        // row, ignored here). Char-code bits 1..3 select the slot.
        const slot = (code >> 1) & 0x03;
        const base = slot * 11;
        glyph = new Uint8Array(10);
        for (let i = 0; i < 10; i++) glyph[i] = cgram[base + i] || 0;
      } else {
        // 8 slots, 8 bytes/slot. Code bits 0..2 select slot.
        const slot = code & 0x07;
        const base = slot * 8;
        glyph = new Uint8Array(8);
        for (let i = 0; i < 8; i++) glyph[i] = cgram[base + i] || 0;
      }
    } else {
      glyph = font5x10 ? rom5x10(code) : rom5x8(code);
    }
    for (let yy = 0; yy < rows; yy++) {
      const row = (glyph[yy] || 0) & 0x1F;
      for (let xx = 0; xx < COLS_PER_CHAR; xx++) {
        bitmap[yy * COLS_PER_CHAR + xx] = (row >> (4 - xx)) & 1;
      }
    }
    return { bitmap, rows };
  }

  // The LCD's colors, from board.css, read once.
  let colors = null;
  function lcdColors() {
    if (!colors) {
      const style = getComputedStyle(document.documentElement);
      const color = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
      colors = { bg: color("--lcd-bg", "#7a9438"), onCol: color("--lcd-on", "#1a2a08"),
                 offCol: color("--lcd-off", "#6e8731") };
    }
    return colors;
  }

  function renderLcd(canvas, lcd) {
    const { rows, cols, ddram, cgram, cur, cur_on, blink_on, disp_on,
            panel_5x10 } = lcd;
    // Cell layout is driven by the panel choice (a hardware decision
    // baked in by --lcd-panel), not by the controller's F-bit.
    //
    // 5x8 panels (16x2, 20x4): each cell is 5x8 dots. The cursor is
    //   rendered as an underline at row 7 (the bottom row of the 8-row
    //   cell) by overlaying the glyph data there -- HD44780 ROM glyphs
    //   leave row 7 blank for exactly this reason.
    //
    // 16x1 5x10 panel: each cell is 5x10 dots for the glyph, plus one
    //   blank backlight row (not drawn as off-pixels), plus a 1-pixel
    //   underline cursor row at the very bottom.
    const font5x10 = !!panel_5x10;
    const glyphRows = font5x10 ? 10 : 8;
    const cursorGap = font5x10 ? 1 : 0;          // backlight row before cursor
    const cursorRow = font5x10 ? 1 : 0;          // extra dot row for cursor
    const rowsPerCell = glyphRows + cursorGap + cursorRow;
    const cellW = COLS_PER_CHAR * (DOT + GAP);
    const cellH = rowsPerCell * (DOT + GAP);
    const padX  = CELL_PAD_X * DOT;
    const padY  = CELL_PAD_Y * DOT;
    const innerW = cols * cellW + (cols - 1) * padX;
    const innerH = rows * cellH + (rows - 1) * padY;
    const W = innerW + LCD_MARGIN * 2;
    const H = innerH + LCD_MARGIN * 2;

    if (canvas.width !== W || canvas.height !== H) {
      canvas.width = W;
      canvas.height = H;
    }
    const ctx = canvas.getContext("2d");

    const { bg, onCol, offCol } = lcdColors();
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    // Blink phase: alternates ~every 400 ms.
    const blinkPhase = (Math.floor(Date.now() / 400) & 1);

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const code = ddram[r * cols + c];
        const cellX0 = LCD_MARGIN + c * (cellW + padX);
        const cellY0 = LCD_MARGIN + r * (cellH + padY);
        const { bitmap } = glyphFor(code, cgram, font5x10);
        const cursorHere = disp_on && cur && cur[0] === r && cur[1] === c;
        const blinkInvert = cursorHere && blink_on && blinkPhase === 0;

        for (let yy = 0; yy < rowsPerCell; yy++) {
          // Backlight gap row (5x10 panel only) -- leave the backlight
          // fill showing through, so no grey unlit-dot pattern appears
          // between the glyph and the cursor row.
          const isGapRow = font5x10 && yy >= glyphRows && yy < glyphRows + cursorGap;
          if (isGapRow) continue;
          for (let xx = 0; xx < COLS_PER_CHAR; xx++) {
            let on;
            if (yy < glyphRows) {
              on = bitmap[yy * COLS_PER_CHAR + xx];
              // 5x8 panel: cursor is the underline on the last glyph
              // row (HD44780 leaves row 7 blank). OR it in here.
              if (!font5x10 && yy === glyphRows - 1 && cursorHere && cur_on) on = 1;
            } else {
              // Dedicated cursor row (5x10 panel only).
              on = (cursorHere && cur_on) ? 1 : 0;
            }
            if (blinkInvert) on = 1;
            ctx.fillStyle = on ? onCol : offCol;
            const px = cellX0 + xx * (DOT + GAP);
            const py = cellY0 + yy * (DOT + GAP);
            ctx.fillRect(px, py, DOT, DOT);
          }
        }
      }
    }
  }

  // ===== Graphic display (ILI9341) =====
  // The display's frame memory arrives as binary messages (tag 0x02) of
  // what changed, in rectangles of runs (../web_display.h has the
  // format), applied to a copy here. The snapshot's gd says how the
  // glass shows it, as ../chips/ili9341.c's ili9341_glass_pixel does:
  // on (else blank, white), the backlight (as brightness), the scans
  // reversed (gs: scan line 0 at the bottom; ss: a line's pixel 0 at the
  // left) and the hardware scroll (VSCRDEF's areas, VSCRSADD).
  const GD_W = 240, GD_LINES = 320;
  const gdMemory = new Uint16Array(GD_W * GD_LINES);
  let gdChanged = true;                 // the memory changed since the glass was drawn

  function applyDisplay(u8) {
    const u16 = (p) => u8[p] | u8[p + 1] << 8;
    const colours = [0x0000, 0xFFFF];   // remembered: the first, then the second
    let p = 1;
    while (p + 5 <= u8.length) {
      const line = u16(p), x = u8[p + 2], w = u8[p + 3] + 1, h = u8[p + 4] + 1;
      p += 5;
      for (let at = 0; at < w * h && p < u8.length; ) {
        const kind = u8[p] >> 6;
        let n = u8[p++] & 63, c = 0;
        if (!n) { n = u16(p); p += 2; }
        if (kind === 1) { c = u16(p); p += 2; colours[1] = colours[0]; colours[0] = c; }
        else if (kind === 2) c = colours[0];
        else if (kind === 3) { c = colours[1]; colours[1] = colours[0]; colours[0] = c; }
        for (const end = Math.min(at + n, w * h); at < end; at++) {
          if (kind === 0) { c = u16(p); p += 2; }
          gdMemory[(line + Math.floor(at / w)) * GD_W + x + at % w] = c;
        }
      }
    }
    gdChanged = true;
  }

  // RGB565 to the canvas's RGBA, as little-endian words
  let rgba565 = null;
  function rgbaTable() {
    if (!rgba565) {
      rgba565 = new Uint32Array(65536);
      for (let v = 0; v < 65536; v++) {
        const r = ((v >> 11) * 527 + 23) >> 6, g = (((v >> 5) & 63) * 259 + 33) >> 6,
              b = ((v & 31) * 527 + 23) >> 6;
        rgba565[v] = (0xFF000000 | b << 16 | g << 8 | r) >>> 0;
      }
    }
    return rgba565;
  }

  // The memory line shown at row y of the glass (0 the top)
  function glassLine(gd, y) {
    const k = gd.gs ? GD_LINES - 1 - y : y;
    const [tfa, vsa, , ssa] = gd.scroll;
    if (k < tfa || k >= tfa + vsa) return k;
    const at = (ssa - tfa + k - tfa) % vsa;
    return tfa + (at < 0 ? at + vsa : at);
  }

  let gdImage = null;
  function renderDisplay(canvas, gd) {
    const ctx = canvas.getContext("2d");
    if (!gdImage) gdImage = ctx.createImageData(GD_W, GD_LINES);
    const out = new Uint32Array(gdImage.data.buffer);
    if (!gd.on) {
      out.fill(0xFFFFFFFF);
    } else {
      const lut = rgbaTable();
      for (let y = 0; y < GD_LINES; y++) {
        const src = glassLine(gd, y) * GD_W, dst = y * GD_W;
        if (gd.ss) for (let x = 0; x < GD_W; x++) out[dst + x] = lut[gdMemory[src + x]];
        else for (let x = 0; x < GD_W; x++) out[dst + x] = lut[gdMemory[src + GD_W - 1 - x]];
      }
    }
    ctx.putImageData(gdImage, 0, 0);
    canvas.style.filter = `brightness(${gd.bl / 255})`;
  }

  // ===== Pins panel =====
  function buildPinTable(table, pins) {
    const hl = pins.hl || {};
    let html = "<tr><th>PORT</th><th colspan=\"8\">bits&nbsp; 7&nbsp; 6&nbsp; 5&nbsp; 4&nbsp; 3&nbsp; 2&nbsp; 1&nbsp; 0</th><th>DDR</th></tr>";
    for (const port of ["a", "b"]) {
      const bits = [7, 6, 5, 4, 3, 2, 1, 0].map((i) => `<td class="b b${i}"></td>`).join("");
      const labels = pins[port].map((l) =>
        `<td${(hl[port] || []).includes(l) ? ' class="hl"' : ""}>${l}</td>`).join("");
      html += `<tr id="row-${port}"><td class="port-name">PORT${port.toUpperCase()}</td>${bits}<td class="ddr"></td></tr>` +
              `<tr id="row-${port}-lbl" class="labels"><td></td>${labels}<td></td></tr>`;
    }
    table.innerHTML = html;
  }

  function fmtBitsRow(rowId, val, ddr) {
    const tr = $(rowId);
    if (!tr) return;
    const cells = tr.querySelectorAll(".b");
    for (let i = 7; i >= 0; i--) {
      const idx = 7 - i;
      const cell = cells[idx];
      const bit = (val >> i) & 1;
      cell.textContent = String(bit);
      cell.classList.toggle("hi", bit === 1);
    }
    tr.querySelector(".ddr").textContent =
      "DDR=$" + ddr.toString(16).padStart(2, "0").toUpperCase();
  }

  // ===== Machines =====
  const machines = {};
  let machineName = null;
  let machine = null;        // the description of the machine on the page

  function define(name, description) {
    machines[name] = description;
  }

  // Build the page for the named machine, in place of any other:
  // header, LEDs, controls, pins.
  function mount(name) {
    machineName = name;
    buttonKeyDown = false;
    machine = machines[name] || null;
    document.body.dataset.machine = name;
    document.title = name;
    if (!machine) {
      $("title").textContent = name;
      $("controls").innerHTML = "";
      $("pin-table").innerHTML = "";
      $("gd-frame").hidden = true;
      setConn("off", `no description for machine "${name}"`);
      return;
    }
    $("title").innerHTML = `${machine.title[0]}<span class="accent">${machine.title[1]}</span>`;

    const indicator = (inner, label) =>
      `<div class="indicator">${inner}<div class="indicator-label">${label}</div></div>`;
    let html = (machine.leds || []).map((led, i) =>
      indicator(`<div class="led${led.red ? " led-red" : ""}" id="${led.id}" data-led="${i}"></div>`, led.label)).join("");
    if (machine.button) {
      html += indicator(`<button class="btn" id="${machine.button.id}" aria-label="control button">` +
                        `<span class="btn-cap"></span></button>`, machine.button.label);
    }
    html += indicator(`<button class="btn btn-reset" id="btn-reset" aria-label="reset (RES) button">` +
                      `<span class="btn-cap">RST</span></button>`, "RESET");
    if (machine.hint) html += `<div class="hint">${machine.hint}</div>`;
    $("controls").innerHTML = html;

    $("btn-reset").addEventListener("click", (e) => { startAudio(); reset(); e.preventDefault(); });
    if (machine.button) {
      const btn = $(machine.button.id);
      btn.addEventListener("pointerdown", (e) => { startAudio(); press(1); e.preventDefault(); });
      btn.addEventListener("pointerup",   () => press(0));
      btn.addEventListener("pointerleave",() => { if (btn.classList.contains("held")) press(0); });
    }
    buildPinTable($("pin-table"), machine.pins);
    $("gd-frame").hidden = !machine.display;
  }

  // The control button, held down or let go.
  function press(down) {
    $(machine.button.id).classList.toggle("held", !!down);
    send({ type: "button", down: down ? 1 : 0 });
  }

  // Keys: on a machine with a keyboard they are typed on it; otherwise
  // the button's key holds the button and the reset key resets.
  let buttonKeyDown = false;
  function onKeyDown(e) {
    if (!machine) return;
    if (machine.keyboard) {
      const text = Keyboard.keyText(e);
      if (text === null) return;
      e.preventDefault();
      Keyboard.messages(text).forEach(send);
    } else if (machine.button && e.key === machine.button.key) {
      if (!buttonKeyDown) { buttonKeyDown = true; startAudio(); press(1); }
      e.preventDefault();
    } else if (machine.resetKey && e.key.toLowerCase() === machine.resetKey) {
      startAudio(); reset(); e.preventDefault();
    }
  }
  function onKeyUp(e) {
    if (machine && machine.button && e.key === machine.button.key && buttonKeyDown) {
      buttonKeyDown = false; press(0); e.preventDefault();
    }
  }
  function onPaste(e) {
    if (!machine || !machine.keyboard) return;
    Keyboard.messages(e.clipboardData.getData("text")).forEach(send);
    e.preventDefault();
  }

  // The board clock's measured rate against its target, flagged when the
  // host can't keep up (the audio breaks up then too).
  function renderSpeed(mhz, target) {
    const el = $("status-speed");
    if (!(mhz > 0)) { el.textContent = ""; return; }
    const shown = mhz.toFixed(2);
    const percent = Math.round(100 * Number(shown) / Number(target.toFixed(2)));
    el.textContent = `clock ${shown} / ${target.toFixed(2)} MHz (${percent}%)`;
    el.classList.toggle("slow", percent < 98);
  }

  // Snapshots are drawn on the next animation frame, the latest one only,
  // so a hidden tab (which gets no animation frames) draws nothing, and
  // the LCD is redrawn only when it (or its cursor's blink) changed, the
  // graphic display only when its memory or its gd changed.
  let latest = null, drawing = false, drawnLcd = null, drawnGd = null;
  function render(s) {
    latest = s;
    if (!drawing) { drawing = true; requestAnimationFrame(draw); }
  }

  function draw() {
    drawing = false;
    const s = latest;
    if (!machine || !s) return;
    const lcdKey = JSON.stringify(s.lcd) + (s.lcd.blink_on ? Math.floor(Date.now() / 400) & 1 : "");
    if (lcdKey !== drawnLcd) { renderLcd($("lcd"), s.lcd); drawnLcd = lcdKey; }
    if (machine.display && s.gd) {
      const gdKey = JSON.stringify(s.gd);
      if (gdChanged || gdKey !== drawnGd) { renderDisplay($("gd"), s.gd); drawnGd = gdKey; gdChanged = false; }
    }
    document.querySelectorAll("[data-led]").forEach((el) => {
      el.classList.toggle("on", !!s.leds[Number(el.dataset.led)]);
    });
    if (machine.button) $(machine.button.id).classList.toggle("held", !!s.btn);
    fmtBitsRow("row-a", s.porta, s.ddra);
    fmtBitsRow("row-b", s.portb, s.ddrb);
    renderSpeed(s.mhz, s.target_mhz);
    $("status-clock").textContent =
      `osc:${s.osc}  cpu:${s.cpu}  pc:$${s.pc.toString(16).padStart(4, "0").toUpperCase()}` +
      (s.stp ? "  [STP]" : "");
  }

  // ===== Audio =====
  // The samples go to an AudioWorklet (audio_worklet.js), which plays
  // them on the audio thread through a jitter buffer (audio_buffer.js),
  // so a late or bursty main thread doesn't break up the sound. Browsers
  // want a gesture before playing, so it starts on the first click or key.
  let audioCtx = null;
  let audioNode = null;
  let audioRate = 22050;
  let audioAt = -Infinity;     // when samples last came

  function startAudio() {
    if (audioCtx) {
      if (audioCtx.state === "suspended") audioCtx.resume();
      return;
    }
    audioCtx = new AudioContext();
    audioCtx.audioWorklet.addModule("/audio_worklet.js").then(() => {
      audioNode = new AudioWorkletNode(audioCtx, "board-audio", { outputChannelCount: [1] });
      audioNode.port.onmessage = (e) => renderAudio(e.data);
      audioNode.port.postMessage({ rate: audioRate });
      audioNode.connect(audioCtx.destination);
    });
  }

  function handleBinary(buf) {
    const u8 = new Uint8Array(buf);
    if (u8.length && u8[0] === 0x02) { applyDisplay(u8); return; }   // 0x02: the graphic display
    if (u8.length < 1 || u8[0] !== 0x01) return;   // 0x01: audio
    audioAt = performance.now();
    if (!audioNode) return;
    const n = (u8.length - 1) >> 1;
    const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    const samples = new Float32Array(n);
    for (let i = 0; i < n; i++) samples[i] = dv.getInt16(1 + i * 2, true) / 32768;
    audioNode.port.postMessage({ samples }, [samples.buffer]);
  }

  // The worklet's buffer: how much it holds, and its gaps so far.
  function renderAudio(stats) {
    const el = $("status-audio");
    if (performance.now() - audioAt > 2000) { el.textContent = ""; return; }   // no audio coming
    el.textContent = `audio ${Math.round(stats.fill * 1000)} ms` +
      (stats.underruns ? `, ${stats.underruns} gap${stats.underruns === 1 ? "" : "s"}` : "");
  }

  // ===== WebSocket =====
  let ws = null;

  function send(obj) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  }

  function setConn(state, msg) {
    const dot = $("status-conn");
    const txt = $("status-text");
    dot.classList.remove("ok", "off");
    dot.classList.add(state === "ok" ? "ok" : "off");
    txt.textContent = msg;
  }

  function connect() {
    setConn("off", "connecting…");
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      setConn("ok", "connected");
      gdMemory.fill(0);          // a new connection sends the whole display
      gdChanged = true;
    };
    ws.onmessage = (e) => {
      if (typeof e.data === "string") {
        let obj;
        try { obj = JSON.parse(e.data); } catch { return; }
        if (obj.type === "hello") {
          // A reconnect can find a different machine on the port.
          if (obj.machine !== machineName) mount(obj.machine);
        } else if (obj.type === "audio_init") {
          audioRate = obj.rate;
          if (audioNode) audioNode.port.postMessage({ rate: audioRate });
        } else if (obj.lcd) {
          render(obj);
        }
      } else {
        handleBinary(e.data);
      }
    };
    ws.onclose = () => { setConn("off", "disconnected, retrying…"); setTimeout(connect, 500); };
    ws.onerror = () => { setConn("off", "ws error"); };
  }

  // Reset button: one-shot {type:"reset"} on click. The server pulses
  // bus->res high for several oscillator ticks; the CPU and VIA see
  // the rising edge and clear their state.
  function reset() {
    const rst = $("btn-reset");
    rst.classList.add("flash");
    setTimeout(() => rst.classList.remove("flash"), 120);
    send({ type: "reset" });
  }

  function start() {
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("keyup", onKeyUp);
    document.addEventListener("paste", onPaste);
    document.addEventListener("click", startAudio);
    document.addEventListener("keydown", startAudio);
    connect();
  }

  return { define, start };
})();
