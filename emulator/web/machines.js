// The boards the page can show, by the name the server's hello gives.
// Board.js builds the page from these:
//   title     the header, plain then accent
//   leds      the LEDs, lit from the snapshot's leds[i] (id for tests)
//   button    a control button held while pressed or while its key is
//             down, shown held from the snapshot's btn
//   resetKey  a key that presses reset (the reset button is always there)
//   keyboard  keys typed or pasted on the page go to the PS/2 keyboard
//   hint      text beside the controls
//   pins      the VIA pin labels, MSB first, and the highlighted ones

Board.define("wendy2c", {
  title: ["wendy", "2c"],
  leds: [
    { id: "led-morse", label: "LED · PB6" },
    { id: "led-control", label: "LED · PA2", red: true },
  ],
  button: { id: "btn-press", label: "BTN · PA1", key: " " },
  resetKey: "r",
  pins: {
    a: ["D7", "D6", "D5", "D4", "RW", "LED", "BTN", "RS"],
    b: ["T1", "LED", "E", "B4", "B3", "B2", "B1", "B0"],
    hl: { a: ["LED", "BTN"], b: ["LED"] },
  },
});

Board.define("michael", {
  title: ["michael ", "v2"],
  leds: [{ id: "led", label: "LED · PA2", red: true }],
  keyboard: true,
  hint: "Type or paste anywhere on the page: the keys go to the PS/2 keyboard.",
  pins: {
    a: ["E", "RW", "RS", "SOEB", "SOLB", "LED", "A1", "A0"],
    b: ["D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0"],
    hl: { a: ["LED"] },
  },
});
