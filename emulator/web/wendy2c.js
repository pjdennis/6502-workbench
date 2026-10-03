// wendy2c's page (see board.js for the shared parts): the control
// button on PA1, held while pressed or while SPACE is down, and R for
// reset. The LEDs are data-led 0 (PB6) and 1 (PA2).

(() => {
  const btn = document.getElementById("btn-press");
  const press = (down) => {
    btn.classList.toggle("held", !!down);
    Board.send({ type: "button", down: down ? 1 : 0 });
  };

  btn.addEventListener("pointerdown", (e) => { Board.unlockAudio(); press(1); e.preventDefault(); });
  btn.addEventListener("pointerup",   () => press(0));
  btn.addEventListener("pointerleave",() => { if (btn.classList.contains("held")) press(0); });

  // Keyboard: space holds the button; 'r' / 'R' triggers reset.
  let spaceDown = false;
  document.addEventListener("keydown", (e) => {
    if (e.key === " " && !spaceDown) {
      spaceDown = true; Board.unlockAudio(); press(1);
      e.preventDefault();
    } else if (e.key === "r" || e.key === "R") {
      Board.unlockAudio(); Board.reset(); e.preventDefault();
    }
  });
  document.addEventListener("keyup", (e) => {
    if (e.key === " ") { spaceDown = false; press(0); e.preventDefault(); }
  });

  Board.start({
    pins: {
      a: ["D7", "D6", "D5", "D4", "RW", "LED", "BTN", "RS"],
      b: ["T1", "LED", "E", "B4", "B3", "B2", "B1", "B0"],
      hl: { a: ["LED", "BTN"], b: ["LED"] },
    },
    onState: (s) => btn.classList.toggle("held", !!s.btn),
  });
})();
