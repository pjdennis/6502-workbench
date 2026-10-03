// michael's page (see board.js for the shared parts): keys typed or
// pasted on the page go to the PS/2 keyboard, as the bytes a terminal
// sends for them (the server encodes them with ps2_keys.c, as --live
// does). The LED is data-led 0 (PA2).

(() => {
  const MAX_BYTES = 64;   // per message: WEB_JSON_BYTES_MAX

  const KEYS = {
    Enter: "\r", Backspace: "\b", Tab: "\t", Escape: "\x1b",
    ArrowUp: "\x1b[A", ArrowDown: "\x1b[B", ArrowRight: "\x1b[C", ArrowLeft: "\x1b[D",
    Home: "\x1b[H", End: "\x1b[F", Insert: "\x1b[2~", Delete: "\x1b[3~",
    PageUp: "\x1b[5~", PageDown: "\x1b[6~",
  };
  const CTRL_KEYS = { ArrowRight: "\x1b[1;5C", ArrowLeft: "\x1b[1;5D" };

  // The terminal bytes for a keydown, or null for keys the keyboard
  // doesn't type (modifiers alone, function keys, browser shortcuts).
  function keyText(e) {
    if (e.altKey || e.metaKey) return null;
    if (e.ctrlKey) {
      if (CTRL_KEYS[e.key]) return CTRL_KEYS[e.key];
      // Ctrl+letter is the control code, except Ctrl+V: that pastes.
      if (/^[a-z]$/i.test(e.key) && e.key.toLowerCase() !== "v")
        return String.fromCharCode(e.key.toUpperCase().charCodeAt(0) - 64);
      return null;
    }
    if (KEYS[e.key]) return KEYS[e.key];
    if (e.key.length === 1 && e.key.charCodeAt(0) >= 0x20 && e.key.charCodeAt(0) < 0x7F) return e.key;
    return null;
  }

  function typeText(text) {
    const bytes = [...text].map((c) => c.charCodeAt(0)).filter((b) => b < 0x80);
    for (let at = 0; at < bytes.length; at += MAX_BYTES)
      Board.send({ type: "keys", bytes: bytes.slice(at, at + MAX_BYTES) });
  }

  document.addEventListener("keydown", (e) => {
    const text = keyText(e);
    if (text === null) return;
    e.preventDefault();
    typeText(text);
  });

  // Pasted lines end in Enter.
  document.addEventListener("paste", (e) => {
    typeText(e.clipboardData.getData("text").replace(/\r\n?/g, "\n"));
    e.preventDefault();
  });

  Board.start({
    pins: {
      a: ["E", "RW", "RS", "SOEB", "SOLB", "LED", "A1", "A0"],
      b: ["D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0"],
      hl: { a: ["LED"] },
    },
  });
})();
