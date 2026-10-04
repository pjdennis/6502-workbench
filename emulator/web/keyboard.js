// Keys for a machine with a PS/2 keyboard (michael): a keydown or pasted
// text as the bytes a terminal sends, which the server types on the
// keyboard with ps2_keys.c, as --live does. Board.js sends them for a
// machine whose description has keyboard: true.

window.Keyboard = (() => {
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

  // The keys messages for text: ASCII only, pasted lines ending in Enter.
  function messages(text) {
    const bytes = [...text.replace(/\r\n?/g, "\n")].map((c) => c.charCodeAt(0)).filter((b) => b < 0x80);
    const out = [];
    for (let at = 0; at < bytes.length; at += MAX_BYTES)
      out.push({ type: "keys", bytes: bytes.slice(at, at + MAX_BYTES) });
    return out;
  }

  return { keyText, messages };
})();
