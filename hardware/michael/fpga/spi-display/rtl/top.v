`timescale 1ns / 1ps
// Michael's SPI display interface on the Cmod A7-35T: pins as in WIRING.md, the bridge in spi_bridge.v.
module top #(
  parameter ACTIVITY_CYCLES = 600_000  // LD1 stays lit this long after each byte (50 ms at 12 MHz)
) (
  input        sysclk,     // 12 MHz
  input  [7:0] d,          // from Michael through the 74LVC245s
  input        e,
  input        csb,
  input        rstb,
  input        dc,
  input        bl,         // backlight level, passed to the display
  output       lcd_cs,
  output       lcd_reset,
  output       lcd_dc,
  output       lcd_mosi,
  output       lcd_sck,
  output       lcd_led,
  output       t_clk,      // touch controller, held idle for now
  output       t_cs,
  output       t_din,
  output [1:0] led         // LD1: display traffic, LD2: display selected
);
  wire selected, accepted;
  spi_bridge bridge (
    .clk(sysclk), .d(d), .e(e), .csb(csb), .rstb(rstb), .dc(dc), .selected(selected), .accepted(accepted),
    .lcd_cs(lcd_cs), .lcd_reset(lcd_reset), .lcd_dc(lcd_dc), .lcd_mosi(lcd_mosi), .lcd_sck(lcd_sck));

  reg [1:0] bl_sync = 2'b11;
  always @(posedge sysclk) bl_sync <= {bl_sync[0], bl};
  assign lcd_led = bl_sync[1];

  assign {t_cs, t_clk, t_din} = 3'b100;

  reg [$clog2(ACTIVITY_CYCLES)-1:0] activity = 0;
  always @(posedge sysclk)
    if (accepted)          activity <= ACTIVITY_CYCLES - 1;
    else if (activity != 0) activity <= activity - 1'b1;
  assign led = {selected, activity != 0};
endmodule
