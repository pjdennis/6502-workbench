`timescale 1ns / 1ps
`include "tb_util.vh"

// Michael (a 2 MHz 65C02 writing its VIA, with the timings of firmware/lib/graphics/graphics_display.inc)
// drives the interface; an ILI9341 model checks the SPI it produces, byte by byte, against what was sent.
module tb_top;
  localparam real CPU_NS = 500.0;  // one 65C02 cycle at 2 MHz
  localparam ACTIVITY_CYCLES = 120;

  reg clk;
  reg [7:0] portb = 8'h00;
  reg e = 1'b0, csb = 1'b1, rstb = 1'b1, dc = 1'b0, bl = 1'b1;
  wire lcd_cs, lcd_reset, lcd_dc, lcd_mosi, lcd_sck, lcd_led, t_clk, t_cs, t_din;
  wire [1:0] led;
  wire d_oeb, d_dir;

  top #(.ACTIVITY_CYCLES(ACTIVITY_CYCLES)) dut (
    .sysclk(clk), .d(portb), .e(e), .csb(csb), .rstb(rstb), .dc(dc), .bl(bl),
    .lcd_cs(lcd_cs), .lcd_reset(lcd_reset), .lcd_dc(lcd_dc), .lcd_mosi(lcd_mosi), .lcd_sck(lcd_sck),
    .lcd_led(lcd_led), .t_clk(t_clk), .t_cs(t_cs), .t_din(t_din), .led(led), .d_oeb(d_oeb), .d_dir(d_dir));

  `TB_CLOCK(clk, 41.667, 10_000_000)  // 12 MHz

  // ---- Michael, and the display ----------------------------------------------------------------------
  // Bytes are expected as E rises, since the FPGA may finish sending a byte before Michael lowers E again.
  `include "../sim/ili9341_model.vh"
  `include "../sim/michael_via.vh"

  // ---- Tests ----------------------------------------------------------------------------------------
  integer i;
  initial begin
    #5000;
    `CHECK_EQ(lcd_cs, 1'b1, "display deselected at start")
    `CHECK_EQ(lcd_reset, 1'b1, "display not held in reset at start")
    `CHECK_EQ({t_cs, t_clk, t_din}, 3'b100, "touch controller idle")
    `CHECK_EQ(lcd_led, 1'b1, "backlight follows bl (high)")
    `CHECK_EQ(led, 2'b00, "status LEDs off while idle")
    `CHECK_EQ({d_oeb, d_dir}, 2'b00, "data buffer enabled, Michael to the FPGA (stage 1 of the bus plan)")

    // Strobes while the display is not selected are someone else's business
    gd_configure;
    for (i = 0; i < 3; i = i + 1) gd_send_data(8'h55 + i);
    expect_all_received;

    // gd_reset: RSTB reaches the display directly, while CSB is still high
    fork
      gd_reset;
      begin cycles(20); `CHECK_EQ(lcd_reset, 1'b0, "display reset while RSTB is low") end
    join
    `CHECK_EQ(lcd_reset, 1'b1, "display reset released with RSTB")

    // A typical sequence: select, commands with parameters, then pixel data at full speed
    gd_select;
    `CHECK_EQ(led[1], 1'b1, "LD2 lit while the display is selected")
    gd_send_command(8'h36); gd_send_data(8'hA8);
    gd_send_command(8'h2A); gd_send_data(8'h00); gd_send_data(8'h00); gd_send_data(8'h00); gd_send_data(8'hEF);
    gd_send_command(8'h2C);
    fast_fill(8'h00, 32);
    fast_fill(8'hFF, 8);
    expect_all_received;
    `CHECK_EQ(led[0], 1'b1, "LD1 flashes on display traffic")

    // Keyboard activity while selected: PA5 (DC) and port B change with E low; nothing may be sent
    for (i = 0; i < 4; i = i + 1) begin cycles(7); dc = ~dc; portb = 8'hC3 ^ i; end
    dc = 1'b1;
    gd_send_data(8'h81);
    expect_all_received;

    // A spike on E (switching noise when port B changes, a few ns to tens of ns) is not a strobe: nothing
    // may be sent
    cycles(10); portb = 8'hA5; #100; e = 1'b1; #90; e = 1'b0; cycles(10);
    expect_all_received;

    // The keyboard interrupt can change PA5 (DC) while a byte is still being shifted out
    cycles(10); portb = 8'h99; cycles(4); expect_byte(8'h99, dc); e = 1'b1; #300; dc = ~dc;
    cycles(4); e = 1'b0; cycles(10); dc = 1'b1;
    expect_all_received;

    // Deselecting while a byte is still being shifted out must not cut it short. Michael's firmware
    // can't deselect that soon at 2 MHz, but could with a faster clock.
    cycles(10); portb = 8'h7E; cycles(4); expect_byte(8'h7E, dc); e = 1'b1; #400; csb = 1'b1;
    cycles(4); e = 1'b0;
    expect_all_received;
    `CHECK_EQ(lcd_cs, 1'b1, "display deselected once the last byte is out")

    // Backlight passes through
    bl = 1'b0; #1000; `CHECK_EQ(lcd_led, 1'b0, "backlight follows bl (low)")
    bl = 1'b1; #1000; `CHECK_EQ(lcd_led, 1'b1, "backlight follows bl (high again)")

    // A reset during a byte abandons it, and the interface works afterwards
    gd_select;
    cycles(4); portb = 8'h3C; cycles(4); e = 1'b1; #300; rstb = 1'b0; cycles(4); e = 1'b0;
    cycles(20); rstb = 1'b1; cycles(20);
    gd_send_command(8'h01); gd_send_data(8'h42);
    expect_all_received;
    gd_unselect;
    #(ACTIVITY_CYCLES * 84 + 2000);
    `CHECK_EQ(led, 2'b00, "status LEDs off again when idle")
    `CHECK_EQ({d_oeb, d_dir}, 2'b00, "data buffer enabled, Michael to the FPGA (stage 1 of the bus plan)")
    `TB_PASS
  end
endmodule
