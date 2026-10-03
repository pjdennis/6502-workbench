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

  top #(.ACTIVITY_CYCLES(ACTIVITY_CYCLES)) dut (
    .sysclk(clk), .d(portb), .e(e), .csb(csb), .rstb(rstb), .dc(dc), .bl(bl),
    .lcd_cs(lcd_cs), .lcd_reset(lcd_reset), .lcd_dc(lcd_dc), .lcd_mosi(lcd_mosi), .lcd_sck(lcd_sck),
    .lcd_led(lcd_led), .t_clk(t_clk), .t_cs(t_cs), .t_din(t_din), .led(led));

  `TB_CLOCK(clk, 41.667, 10_000_000)  // 12 MHz

  // ---- Michael ----------------------------------------------------------------------------------
  task cycles(input integer n); #(n * CPU_NS); endtask

  // Bytes the display should receive, in order, with the DC level each is sent with. Recorded as E
  // rises, since the FPGA may finish sending a byte before Michael lowers E again.
  reg [7:0] exp_byte [0:1023];
  reg       exp_dc   [0:1023];
  integer   n_exp = 0;
  task expect_byte(input [7:0] b, input d);
    begin exp_byte[n_exp] = b; exp_dc[n_exp] = d; n_exp = n_exp + 1; end
  endtask

  task gd_configure;   begin cycles(8); e = 1'b0; cycles(8); {rstb, csb} = 2'b11; end endtask
  task gd_reset;       begin cycles(6); rstb = 1'b0; cycles(40); rstb = 1'b1; cycles(40); end endtask
  task gd_select;      begin cycles(11); dc = 1'b1; cycles(8); csb = 1'b0; cycles(10); end endtask
  task gd_unselect;    begin cycles(11); csb = 1'b1; cycles(8); dc = 1'b0; cycles(10); end endtask

  // jsr gd_send_data: sta PORTB / lda #GD_E / tsb GD_PORT / trb GD_PORT / rts
  task gd_send_data(input [7:0] b);
    begin
      cycles(6 + 4); portb = b;
      cycles(2 + 6); if (!csb) expect_byte(b, dc); e = 1'b1;
      cycles(6);     e = 1'b0;
      cycles(6);
    end
  endtask

  // gd_send_command: DC low for one byte, high again after E has fallen
  task gd_send_command(input [7:0] b);
    begin cycles(3 + 2 + 6); dc = 1'b0; cycles(4); gd_send_data(b); cycles(2 + 6); dc = 1'b1; cycles(6); end
  endtask

  // send_zero_data's unrolled loop: sta PORTA,Y (E high) / stx PORTA (E low), one byte every 9 cycles
  task fast_fill(input [7:0] b, input integer n);
    integer i;
    begin
      cycles(4); portb = b;
      for (i = 0; i < n; i = i + 1) begin
        cycles(5); expect_byte(b, dc); e = 1'b1;
        cycles(4); e = 1'b0;
      end
    end
  endtask

  // ---- ILI9341 (4-wire SPI, mode 0, MSB first) ------------------------------------------------------
  integer n_rx = 0, bits = 0;
  reg [7:0] sr;
  reg dc_first;
  realtime last_rise = -1.0e9, mosi_change = -1.0e9, cs_fall = -1.0e9;

  always @(lcd_mosi) mosi_change = $realtime;
  always @(negedge lcd_cs) cs_fall = $realtime;
  always @(negedge lcd_reset) bits = 0;  // a hardware reset abandons a partial byte
  always @(posedge lcd_cs) if (lcd_reset) `CHECK_EQ(bits, 0, "CS released in the middle of a byte")

  always @(posedge lcd_sck) if (lcd_reset) begin
    `CHECK_EQ(lcd_cs, 1'b0, "SCK pulse while CS is high")
    `CHECK($realtime - last_rise >= 100.0, "SCK faster than the ILI9341's 100 ns write cycle")
    `CHECK($realtime - mosi_change >= 30.0, "MOSI setup before SCK under 30 ns")
    `CHECK($realtime - cs_fall >= 40.0, "CS to first SCK under 40 ns")
    if (bits == 0) dc_first = lcd_dc;
    else `CHECK_EQ(lcd_dc, dc_first, "DC changed within a byte")
    sr = {sr[6:0], lcd_mosi};
    bits = bits + 1;
    if (bits == 8) begin
      `CHECK(n_rx < n_exp, "display received a byte that Michael never sent")
      `CHECK_EQ(sr, exp_byte[n_rx], "byte received by the display")
      `CHECK_EQ(dc_first, exp_dc[n_rx], "DC of the byte received by the display")
      n_rx = n_rx + 1;
      bits = 0;
    end
    last_rise = $realtime;
  end

  task expect_all_received;
    begin #5000; `CHECK_EQ(n_rx, n_exp, "bytes received by the display") end
  endtask

  // ---- Tests ----------------------------------------------------------------------------------------
  integer i;
  initial begin
    #5000;
    `CHECK_EQ(lcd_cs, 1'b1, "display deselected at start")
    `CHECK_EQ(lcd_reset, 1'b1, "display not held in reset at start")
    `CHECK_EQ({t_cs, t_clk, t_din}, 3'b100, "touch controller idle")
    `CHECK_EQ(lcd_led, 1'b1, "backlight follows bl (high)")
    `CHECK_EQ(led, 2'b00, "status LEDs off while idle")

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
    `TB_PASS
  end
endmodule
