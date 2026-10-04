`timescale 1ns / 1ps
`include "tb_util.vh"

// display_spi.v: queued data and command bytes reach an ILI9341 model in order, with their DC levels and
// within its SPI timing; reset and backlight entries take effect in their turn; CS is high when idle.
module tb_display_spi;
  reg clk;
  `TB_CLOCK(clk, 41.667, 20_000_000)  // 12 MHz

  localparam DATA = 2'd0, COMMAND = 2'd1, RESET = 2'd2, BACKLIGHT = 2'd3;
  reg        push = 1'b0;
  reg  [1:0] kind = DATA;
  reg  [7:0] value = 8'h00;
  wire       full, busy, lcd_cs, lcd_reset, lcd_dc, lcd_mosi, lcd_sck, lcd_led;
  display_spi #(.QUEUE_DEPTH(16)) dut (
    .clk(clk), .push(push), .kind(kind), .value(value), .full(full), .busy(busy),
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
    `CHECK_EQ(lcd_cs, 1'b0, "selected while bytes are queued")
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
    queue(BACKLIGHT, 8'd255); wait_idle; measure_backlight;
    `CHECK_EQ(high, 256, "backlight fully on again")

    // The queue fills (16 entries here) while a byte goes out
    for (i = 0; i < 17; i = i + 1) begin kind = DATA; value = i; push = 1; expect_byte(i, 1'b1); @(posedge clk); #1; end
    push = 0;
    `CHECK_EQ(full, 1'b1, "full")
    `TB_PASS
  end
endmodule
