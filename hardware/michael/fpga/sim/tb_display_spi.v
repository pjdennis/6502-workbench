`timescale 1ns / 1ps
`include "tb_util.vh"

// display_spi.v: queued data and command bytes reach an ILI9341 model in order, with their DC levels and
// within its SPI timing; reset and backlight entries take effect in their turn; CS is high when idle. The
// backlight's PWM edges disturb the SPI lines on the board (snow on the display), so the backlight only
// changes while CS is high, and no byte starts within 1 us of a change. A second source, the text renderer,
// has bytes of its own: queued entries go first between its runs, and wait while it's in the middle of one
// (r_lock), so nothing lands inside a character's bytes.
module tb_display_spi;
  reg clk;
  `TB_CLOCK(clk, 41.667, 20_000_000)  // 12 MHz

  localparam DATA = 2'd0, COMMAND = 2'd1, RESET = 2'd2, BACKLIGHT = 2'd3;
  reg        push = 1'b0;
  reg  [1:0] kind = DATA;
  reg  [7:0] value = 8'h00;
  wire       full, busy, lcd_cs, lcd_reset, lcd_dc, lcd_mosi, lcd_sck, lcd_led, r_take;
  reg        r_valid = 1'b0, r_lock = 1'b0;
  reg  [1:0] r_kind = DATA;
  reg  [7:0] r_value = 8'h00;
  display_spi #(.QUEUE_DEPTH(16)) dut (
    .clk(clk), .push(push), .kind(kind), .value(value), .full(full), .busy(busy),
    .r_valid(r_valid), .r_kind(r_kind), .r_value(r_value), .r_lock(r_lock), .r_take(r_take),
    .lcd_cs(lcd_cs), .lcd_reset(lcd_reset), .lcd_dc(lcd_dc), .lcd_mosi(lcd_mosi), .lcd_sck(lcd_sck),
    .lcd_led(lcd_led));

  `include "../sim/ili9341_model.vh"

  task queue(input [1:0] k, input [7:0] v);
    begin
      kind = k; value = v; push = 1'b1;
      @(posedge clk); #1 push = 1'b0;
      if (k == DATA) expect_byte(v, 1'b1);
      if (k == COMMAND) expect_byte(v, 1'b0);
    end
  endtask

  task wait_idle; begin while (busy) @(posedge clk); #1; end endtask

  // The backlight's duty cycle over a PWM period (256 clocks), in clocks
  integer high;
  task measure_backlight;
    integer c;
    begin high = 0; for (c = 0; c < 256; c = c + 1) begin @(posedge clk); high = high + lcd_led; end end
  endtask

  // Watches every backlight change against the SPI lines
  integer led_while_selected = 0, sck_near_led = 0, since_led = 1000;
  reg     led_before = 1'b1;
  always @(posedge clk) begin
    since_led <= lcd_led != led_before ? 0 : since_led + 1;
    if (lcd_led != led_before && !lcd_cs) led_while_selected = led_while_selected + 1;
    led_before <= lcd_led;
  end
  always @(posedge lcd_sck) if (since_led < 12) sck_near_led = sck_near_led + 1;

  // The renderer's run of bytes (a command, then data), locked from its first byte's going to its last's
  reg [7:0] run [0:7];
  integer   run_n = 0, run_i;
  task render;
    begin
      for (run_i = 0; run_i < run_n; run_i = run_i + 1) begin
        r_kind = run_i == 0 ? COMMAND : DATA; r_value = run[run_i]; r_valid = 1'b1;
        @(posedge clk); while (!r_take) @(posedge clk);
        #1 r_lock = run_i != run_n - 1;
      end
      r_valid = 1'b0;
    end
  endtask

  integer i;
  initial begin
    repeat (4) @(posedge clk); #1;
    `CHECK_EQ({lcd_cs, lcd_reset, busy}, 3'b110, "idle: deselected, out of reset, not busy")
    measure_backlight;
    `CHECK_EQ(high, 256, "backlight fully on at start")

    // A command and its parameters, then a burst of data, queued faster than they go out
    queue(COMMAND, 8'h2A); queue(DATA, 8'h00); queue(DATA, 8'hEF);
    queue(COMMAND, 8'h2C);
    for (i = 0; i < 12; i = i + 1) queue(DATA, 8'hF0 + i);
    `CHECK_EQ(busy, 1'b1, "busy while bytes are queued")
    `CHECK_EQ(lcd_cs, 1'b0, "selected while a byte goes out")
    wait_idle;
    expect_all_received;
    `CHECK_EQ(lcd_cs, 1'b1, "deselected once the queue is empty")

    // Reset: in its turn, after the bytes before it
    queue(DATA, 8'h5A); queue(RESET, 8'h00);
    `CHECK_EQ(lcd_reset, 1'b1, "reset waits for the byte before it")
    wait_idle;
    `CHECK_EQ(lcd_reset, 1'b0, "reset low");
    queue(RESET, 8'h01); wait_idle;
    `CHECK_EQ(lcd_reset, 1'b1, "reset released");
    expect_all_received;

    // Backlight brightness by PWM: 0 is off, 128 half
    queue(BACKLIGHT, 8'd0); wait_idle; measure_backlight;
    `CHECK_EQ(high, 0, "backlight off")
    queue(BACKLIGHT, 8'd128); wait_idle; measure_backlight;
    `CHECK_EQ(high, 128, "backlight at half")

    // A stream of bytes while the backlight is dimmed: they all arrive, and the PWM keeps clear of them
    for (i = 0; i < 300; i = i + 1) begin queue(DATA, i); repeat (14 + i % 7) @(posedge clk); #1; end
    wait_idle;
    expect_all_received;
    `CHECK_EQ(led_while_selected, 0, "no backlight change while selected")
    `CHECK_EQ(sck_near_led, 0, "no SCK within 1 us of a backlight change")

    queue(BACKLIGHT, 8'd255); wait_idle; measure_backlight;
    `CHECK_EQ(high, 256, "backlight fully on again")

    // The renderer: queued entries go first, then its run; entries queued during the run wait for its end
    run[0] = 8'h2C; run[1] = 8'hA1; run[2] = 8'hA2; run[3] = 8'hA3; run_n = 4;
    queue(DATA, 8'h11);
    expect_byte(8'h2C, 1'b0); expect_byte(8'hA1, 1'b1); expect_byte(8'hA2, 1'b1); expect_byte(8'hA3, 1'b1);
    fork
      render;
      begin repeat (40) @(posedge clk); #1 queue(DATA, 8'h22); queue(BACKLIGHT, 8'd255); end
    join
    wait_idle;
    expect_all_received;

    // The queue fills (16 entries here) while a byte goes out
    for (i = 0; i < 17; i = i + 1) begin kind = DATA; value = i; push = 1; expect_byte(i, 1'b1); @(posedge clk); #1; end
    push = 0;
    `CHECK_EQ(full, 1'b1, "full")
    `TB_PASS
  end
endmodule
